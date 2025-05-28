import unittest
from app import app, db, bcrypt # app, db, bcrypt を適切にインポート
from app.models import User

class AuthTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # フォームテストのためにCSRFを無効化
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # インメモリDBを使用
        self.app = app.test_client()
        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_successful_registration(self):
        # 新しいユーザーを登録
        response = self.app.post('/register', data=dict(
            username='testuser',
            password='password123',
            confirm_password='password123'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200) # 登録後のリダイレクト先がOKか
        # Check if the success message is flashed
        self.assertIn(b'Your account has been created! You are now able to log in', response.data)
        with app.app_context():
            user = User.query.filter_by(username='testuser').first()
            self.assertIsNotNone(user)
            # email属性がないことを確認 (If email attribute truly does not exist)
            self.assertFalse(hasattr(user, 'email'))

    def test_duplicate_username_registration(self):
        # 最初のユーザーを登録
        self.app.post('/register', data=dict(
            username='testuser',
            password='password123',
            confirm_password='password123'
        ), follow_redirects=True)
        # 同じユーザー名で再度登録
        response = self.app.post('/register', data=dict(
            username='testuser',
            password='anotherpassword',
            confirm_password='anotherpassword'
        ), follow_redirects=True)
        self.assertIn(b'That username is taken. Please choose a different one.', response.data) # エラーメッセージを確認

    def test_successful_login(self):
        # まずユーザーを登録
        with app.app_context():
            hashed_password = bcrypt.generate_password_hash('password123').decode('utf-8')
            user = User(username='loginuser', password=hashed_password)
            db.session.add(user)
            db.session.commit()

        response = self.app.post('/login', data=dict(
            username='loginuser',
            password='password123'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200) # ログイン後のホームページなど
        # Check for a common element on the home page after login, e.g., "Logout" link or welcome message
        # Assuming home page after login contains "Account" or "Logout" link
        self.assertTrue(b'Account' in response.data or b'Logout' in response.data)


    def test_login_nonexistent_user(self):
        response = self.app.post('/login', data=dict(
            username='nouser',
            password='password123'
        ), follow_redirects=True)
        self.assertIn(b'Login Unsuccessful. Please check username and password', response.data)

    def test_login_incorrect_password(self):
        # ユーザーを登録
        with app.app_context():
            hashed_password = bcrypt.generate_password_hash('password123').decode('utf-8')
            user = User(username='loginuser2', password=hashed_password)
            db.session.add(user)
            db.session.commit()

        response = self.app.post('/login', data=dict(
            username='loginuser2',
            password='wrongpassword'
        ), follow_redirects=True)
        self.assertIn(b'Login Unsuccessful. Please check username and password', response.data)

if __name__ == '__main__':
    # To ensure the app context is available for imports if tests are run directly
    # and app structure relies on it.
    # However, typically flask test runner or unittest discovery handles this.
    # For simplicity, direct execution `python tests.py` should work with this structure.
    unittest.main()
