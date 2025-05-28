import os
import json
from datetime import datetime, date
from werkzeug.utils import secure_filename
from flask import render_template, url_for, flash, redirect, request, jsonify, current_app, send_file
from sqlalchemy import or_ # Import or_ for search queries
from io import BytesIO # For sending files
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from xhtml2pdf import pisa  # For PDF export
from app import app, db, bcrypt
from app.forms import (
    RegistrationForm, LoginForm, 
    ExperimentFormatForm, FieldDefinitionForm, FormatPatternForm,
    CreateExperimentInstanceForm, generate_dynamic_data_form,
    # Plate Layout Forms
    PlateLayoutForm, WellPropertyDefinitionForm, LinkPlateToExperimentForm, generate_well_data_form
)
from app.models import (
    User, ExperimentFormat, FieldDefinition, FormatPattern,
    ExperimentInstance, ExperimentFieldValue, ExperimentChangeLog,
    # Plate Layout Models
    PlateLayout, WellPropertyDefinition, ExperimentPlateLink, WellData
)
from flask_login import login_user, current_user, logout_user, login_required

# Helper function to save uploaded files
def save_file(form_file_data, experiment_id, field_id):
    if not form_file_data:
        return None
    
    filename = secure_filename(form_file_data.filename)
    # Create a unique path for each experiment's files to avoid name collisions
    exp_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(experiment_id), str(field_id))
    if not os.path.exists(exp_upload_folder):
        os.makedirs(exp_upload_folder)
        
    file_path = os.path.join(exp_upload_folder, filename)
    form_file_data.save(file_path)
    # Store a relative path to be used with url_for('static', ...) or a custom serve view
    # For simplicity, storing path from 'static' onwards.
    # Ensure UPLOAD_FOLDER is 'static/uploads' or similar for this to work directly with static endpoint.
    # static_path = os.path.join('uploads', str(experiment_id), str(field_id), filename)
    # Or store the full path and serve files via a dedicated route if UPLOAD_FOLDER is outside static
    return file_path # Or static_path, depending on serving strategy

# Helper function to log changes
def log_experiment_change(instance_id, user_id, field_name, old_value, new_value):
    # Avoid logging if value hasn't actually changed
    if str(old_value) == str(new_value): # Compare as strings to handle various types
        return

    change = ExperimentChangeLog(
        experiment_instance_id=instance_id,
        user_id=user_id,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None
    )
    db.session.add(change)

# Existing User Auth Routes

@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html', title='Home')

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route("/account")
@login_required
def account():
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account', image_file=image_file)

# Experiment Format Routes (Existing - Keep them)
@app.route("/formats")
@login_required
def list_experiment_formats():
    search_term = request.args.get('search', '')
    if search_term:
        formats = ExperimentFormat.query.filter(
            (ExperimentFormat.name.ilike(f'%{search_term}%')) |
            (ExperimentFormat.description.ilike(f'%{search_term}%'))
        ).order_by(ExperimentFormat.name).all()
    else:
        formats = ExperimentFormat.query.order_by(ExperimentFormat.name).all()
    return render_template('list_formats.html', formats=formats, title="Experiment Formats", search_term=search_term)

@app.route("/formats/new", methods=['GET', 'POST'])
@login_required
def create_experiment_format():
    form = ExperimentFormatForm()
    if form.validate_on_submit():
        new_format = ExperimentFormat(name=form.name.data, description=form.description.data)
        db.session.add(new_format)
        db.session.commit()
        flash('Experiment format created successfully!', 'success')
        return redirect(url_for('edit_experiment_format', format_id=new_format.id))
    return render_template('create_format.html', title='Create Experiment Format', form=form)

@app.route("/formats/<int:format_id>/view")
@login_required
def view_experiment_format(format_id):
    exp_format = ExperimentFormat.query.get_or_404(format_id)
    return render_template('view_format.html', title=exp_format.name, format=exp_format)

@app.route("/formats/<int:format_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_experiment_format(format_id):
    exp_format = ExperimentFormat.query.get_or_404(format_id)
    form = ExperimentFormatForm(obj=exp_format)
    field_form = FieldDefinitionForm()

    if form.validate_on_submit() and 'submit_format' in request.form:
        exp_format.name = form.name.data
        exp_format.description = form.description.data
        db.session.commit()
        flash('Experiment format updated!', 'success')
        return redirect(url_for('edit_experiment_format', format_id=exp_format.id))

    if field_form.validate_on_submit() and 'submit_field' in request.form:
        new_field = FieldDefinition(
            name=field_form.name.data, field_type=field_form.field_type.data,
            units=field_form.units.data if field_form.field_type.data == "NUMBER" else None,
            is_required=field_form.is_required.data,
            dropdown_options=field_form.dropdown_options.data if field_form.field_type.data == "DROPDOWN" else None,
            experiment_format_id=exp_format.id
        )
        db.session.add(new_field)
        db.session.commit()
        flash('Field added successfully!', 'success')
        return redirect(url_for('edit_experiment_format', format_id=exp_format.id))
        
    return render_template('edit_format.html', title=f'Edit {exp_format.name}', 
                           format_form=form, field_form=field_form, format=exp_format)

@app.route("/formats/<int:format_id>/delete", methods=['POST'])
@login_required
def delete_experiment_format(format_id):
    exp_format = ExperimentFormat.query.get_or_404(format_id)
    if exp_format.instances: # Check if format is in use
        flash('This format is in use by one or more experiments and cannot be deleted.', 'danger')
        return redirect(url_for('list_experiment_formats'))
    db.session.delete(exp_format)
    db.session.commit()
    flash('Experiment format deleted successfully.', 'success')
    return redirect(url_for('list_experiment_formats'))

@app.route("/formats/field/<int:field_id>/delete", methods=['POST'])
@login_required
def delete_field_definition(field_id):
    field = FieldDefinition.query.get_or_404(field_id)
    format_id = field.experiment_format_id
    # Check if data exists for this field in any experiment instance
    if ExperimentFieldValue.query.filter_by(field_definition_id=field.id).first():
        flash(f'Field "{field.name}" has data in one or more experiments and cannot be deleted. Consider archiving the format or field if possible.', 'danger')
        return redirect(url_for('edit_experiment_format', format_id=format_id))
    db.session.delete(field)
    db.session.commit()
    flash('Field definition deleted successfully.', 'success')
    return redirect(url_for('edit_experiment_format', format_id=format_id))

@app.route("/formats/<int:format_id>/patterns/new", methods=['GET', 'POST'])
@login_required
def create_format_pattern(format_id):
    exp_format = ExperimentFormat.query.get_or_404(format_id)
    form = FormatPatternForm()
    if form.validate_on_submit():
        try:
            pattern_data = json.loads(form.pattern_data_json.data) if form.pattern_data_json.data else None
        except json.JSONDecodeError:
            flash('Invalid JSON data in pattern.', 'danger')
            return render_template('create_pattern.html', title='Create New Pattern', form=form, format=exp_format)
        
        pattern = FormatPattern(
            name=form.name.data, description=form.description.data,
            experiment_format_id=exp_format.id, pattern_data=pattern_data
        )
        db.session.add(pattern)
        db.session.commit()
        flash('Pattern created successfully!', 'success')
        return redirect(url_for('view_experiment_format', format_id=exp_format.id))
    return render_template('create_pattern.html', title='Create New Pattern', form=form, format=exp_format)

# Experiment Instance Routes
@app.route("/experiments")
@login_required
def list_experiments():
    page = request.args.get('page', 1, type=int)
    query = ExperimentInstance.query.order_by(ExperimentInstance.last_modified_date.desc())

    # Filtering
    search_title = request.args.get('search_title')
    status_filter = request.args.get('status_filter')
    format_filter = request.args.get('format_filter', type=int)

    if search_title:
        query = query.filter(ExperimentInstance.title.ilike(f'%{search_title}%'))
    if status_filter:
        query = query.filter(ExperimentInstance.status == status_filter)
    if format_filter:
        query = query.filter(ExperimentInstance.format_id == format_filter)

    experiments = query.paginate(page=page, per_page=10) # 10 experiments per page
    status_choices = CreateExperimentInstanceForm().status.choices # Get choices from form
    all_formats = ExperimentFormat.query.order_by(ExperimentFormat.name).all()
    all_users = User.query.order_by(User.username).all() # For filtering by user
    
    # Get date range from request args
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    user_filter = request.args.get('user_filter', type=int)

    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            query = query.filter(ExperimentInstance.experiment_date >= date_from)
        except ValueError:
            flash('Invalid "Date From" format. Please use YYYY-MM-DD.', 'warning')
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            query = query.filter(ExperimentInstance.experiment_date <= date_to)
        except ValueError:
            flash('Invalid "Date To" format. Please use YYYY-MM-DD.', 'warning')
    
    if user_filter:
        query = query.filter(ExperimentInstance.user_id == user_filter)

    experiments = query.paginate(page=page, per_page=10) 
        
    return render_template('experiments/list_experiments.html', experiments=experiments, title="Experiments",
                           status_choices=status_choices, all_formats=all_formats, all_users=all_users,
                           search_title=search_title, status_filter=status_filter, format_filter=format_filter,
                           date_from=date_from_str, date_to=date_to_str, user_filter=user_filter)


@app.route("/experiments/new", methods=['GET', 'POST'])
@login_required
def create_experiment_instance():
    form = CreateExperimentInstanceForm()
    # Dynamically set choices for experiment_format if needed, or rely on QuerySelectField
    # form.experiment_format.query = ExperimentFormat.query.order_by(ExperimentFormat.name).all()
    
    if form.validate_on_submit():
        # Create instance but don't commit yet, redirect to data entry page
        # Or, create and then go to edit page which will also serve as data entry
        instance = ExperimentInstance(
            title=form.title.data,
            experiment_date=form.experiment_date.data,
            status=form.status.data,
            user_id=current_user.id,
            format_id=form.experiment_format.data.id 
        )
        db.session.add(instance)
        db.session.flush() # Get the ID for the instance before committing
        
        log_experiment_change(instance.id, current_user.id, "Experiment", None, "Created")
        db.session.commit()
        
        flash('Experiment shell created. Proceed to enter data.', 'success')
        return redirect(url_for('edit_experiment_instance', instance_id=instance.id))
        
    return render_template('experiments/create_experiment_instance.html', title='Create New Experiment', form=form)

@app.route("/experiments/<int:instance_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_experiment_instance(instance_id):
    instance = ExperimentInstance.query.get_or_404(instance_id)
    if instance.author != current_user and not current_user.is_admin: # Assuming an is_admin property or role
        flash('You do not have permission to edit this experiment.', 'danger')
        return redirect(url_for('list_experiments'))

    exp_format = instance.experiment_format_ref
    
    # Prepare existing values for the dynamic form
    existing_values = {fv.field_definition_id: fv.value for fv in instance.field_values}

    # Generate the dynamic data entry form
    # For GET, pass existing_values. For POST, pass request.form.
    dynamic_data_form = generate_dynamic_data_form(exp_format, data=request.form if request.method == 'POST' else None, existing_values=existing_values)

    if dynamic_data_form.validate_on_submit() and 'submit_data' in request.form : # Check if the data form was submitted
        # Process and save data from the dynamic form
        for field_def in exp_format.fields:
            form_field_name = f"field_{field_def.id}"
            submitted_value_obj = getattr(dynamic_data_form, form_field_name)
            
            if submitted_value_obj:
                submitted_value = submitted_value_obj.data
                
                # Handle file uploads
                if field_def.field_type == 'FILE':
                    if isinstance(submitted_value, str): # Already a path (no new file uploaded)
                        # If we want to allow file deletion, need a checkbox or similar
                        # For now, if string, it means no new file.
                        # If empty string and field is optional, it could mean remove file.
                        # This part needs careful thought on how to handle existing files.
                        # For now, if a path is there, and no new file, keep it.
                        # If a new file is uploaded, submitted_value will be FileStorage.
                         pass # Keep existing file path if no new file
                    elif submitted_value: # New file uploaded (FileStorage object)
                        # Delete old file if it exists and a new one is uploaded
                        old_field_value_obj = ExperimentFieldValue.query.filter_by(
                            experiment_instance_id=instance.id,
                            field_definition_id=field_def.id
                        ).first()
                        if old_field_value_obj and old_field_value_obj.value:
                            try:
                                old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], old_field_value_obj.value) # Assuming value is relative path from UPLOAD_FOLDER
                                if os.path.exists(old_file_path):
                                     os.remove(old_file_path)
                            except Exception as e:
                                app.logger.error(f"Error deleting old file {old_field_value_obj.value}: {e}")

                        relative_file_path = save_file(submitted_value, instance.id, field_def.id)
                        # Adjust path to be relative from static folder if UPLOAD_FOLDER is static/uploads
                        if relative_file_path and app.config['UPLOAD_FOLDER'].endswith('static/uploads'):
                             # Example: static/uploads/exp_id/field_id/filename.txt -> uploads/exp_id/field_id/filename.txt
                            base_static_uploads = os.path.join('static', 'uploads') 
                            if app.config['UPLOAD_FOLDER'].startswith(base_static_uploads):
                                 # Path relative to 'static' directory
                                 # We want path relative to UPLOAD_FOLDER's parent ('static')
                                 # So, if UPLOAD_FOLDER is /app/static/uploads, and file is /app/static/uploads/1/1/f.txt
                                 # We want to store 'uploads/1/1/f.txt'
                                 # This needs to be robust if paths change.
                                 # A simpler way is to store path from UPLOAD_FOLDER and construct URL dynamically
                                 # For now, storing the part after 'static/'
                                 # This is brittle. Better to store path from UPLOAD_FOLDER root.
                                 # And build URL with a dedicated view or ensure UPLOAD_FOLDER is directly servable.
                                 # For simplicity, assume UPLOAD_FOLDER is 'app/static/uploads'
                                 # and we store 'uploads/exp_id/field_id/filename'
                                 # This requires UPLOAD_FOLDER to be configured as app.root_path + '/static/uploads'
                                 # Let's adjust save_file to return path relative to UPLOAD_FOLDER itself.
                                 # And store that. Then construct full URL in template.
                                 # Path returned by save_file: /app/static/uploads/exp_id/field_id/filename.txt
                                 # We need: uploads/exp_id/field_id/filename.txt
                                 # static_part = os.path.join(app.root_path, 'static')
                                 # submitted_value = os.path.relpath(relative_file_path, static_part)
                                 # This is complex. Let's store path from UPLOAD_FOLDER root.
                                 # save_file returns full path. We need to make it relative to UPLOAD_FOLDER.
                                submitted_value = os.path.relpath(relative_file_path, app.config['UPLOAD_FOLDER'])

                    else: # No file uploaded or cleared
                        submitted_value = None # Or handle deletion if a mechanism is added


                # For Checkbox (BooleanField), WTForms gives True/False. Convert to string if needed or store as is.
                if field_def.field_type == 'CHECKBOX':
                    submitted_value = str(submitted_value) # Store as 'True' or 'False' string

                # Get existing value or create new
                field_value_obj = ExperimentFieldValue.query.filter_by(
                    experiment_instance_id=instance.id,
                    field_definition_id=field_def.id
                ).first()
                
                old_db_value = None
                if field_value_obj:
                    old_db_value = field_value_obj.value
                    if field_value_obj.value != submitted_value:
                        field_value_obj.value = submitted_value
                else:
                    field_value_obj = ExperimentFieldValue(
                        experiment_instance_id=instance.id,
                        field_definition_id=field_def.id,
                        value=submitted_value
                    )
                    db.session.add(field_value_obj)
                
                log_experiment_change(instance.id, current_user.id, field_def.name, old_db_value, submitted_value)

        instance.last_modified_date = datetime.utcnow()
        db.session.commit()
        flash('Experiment data saved successfully!', 'success')
        return redirect(url_for('view_experiment_instance', instance_id=instance.id))

    # For GET request, populate the main instance details form
    main_details_form = CreateExperimentInstanceForm(obj=instance)
    main_details_form.experiment_format.data = instance.experiment_format_ref # QuerySelectField needs object

    # If main details form (title, status, etc.) is submitted
    if main_details_form.validate_on_submit() and 'submit_details' in request.form:
        log_experiment_change(instance.id, current_user.id, "Title", instance.title, main_details_form.title.data)
        log_experiment_change(instance.id, current_user.id, "Experiment Date", str(instance.experiment_date), str(main_details_form.experiment_date.data))
        log_experiment_change(instance.id, current_user.id, "Status", instance.status, main_details_form.status.data)
        # Format cannot be changed after creation for simplicity now
        
        instance.title = main_details_form.title.data
        instance.experiment_date = main_details_form.experiment_date.data
        instance.status = main_details_form.status.data
        instance.last_modified_date = datetime.utcnow()
        db.session.commit()
        flash('Experiment details updated!', 'success')
        return redirect(url_for('edit_experiment_instance', instance_id=instance.id))


    return render_template('experiments/edit_experiment_instance.html', 
                           title=f"Edit: {instance.title}", 
                           instance=instance, 
                           main_details_form=main_details_form, # For title, date, status
                           dynamic_data_form=dynamic_data_form, # For field values
                           format=exp_format)


@app.route("/experiments/<int:instance_id>")
@login_required
def view_experiment_instance(instance_id):
    instance = ExperimentInstance.query.get_or_404(instance_id)
    # field_values are mapped by field_definition.name for easier template access
    # This is tricky because multiple field_values can exist if not careful
    # Better to pass the raw field_values and let template iterate
    # Or create a dictionary:
    # values_dict = {fv.field_definition_ref.name: fv.value for fv in instance.field_values}
    # For files, need to construct URL:
    # file_urls = {}
    # for fv in instance.field_values:
    #    if fv.field_definition_ref.field_type == 'FILE' and fv.value:
    #        # Assuming fv.value is path relative to UPLOAD_FOLDER
    #        # And UPLOAD_FOLDER is 'static/uploads'
    #        file_urls[fv.field_definition_id] = url_for('static', filename=f"uploads/{fv.value}")
    # This also needs adjustment based on how paths are stored.
    # If fv.value is like 'exp_id/field_id/filename.txt' (relative to UPLOAD_FOLDER)
    # and UPLOAD_FOLDER is 'app/static/uploads', then url is 'static', 'uploads/' + fv.value
    
    change_logs = ExperimentChangeLog.query.filter_by(experiment_instance_id=instance.id).order_by(ExperimentChangeLog.timestamp.desc()).all()
    
    return render_template('experiments/view_experiment_instance.html', 
                           title=f"View: {instance.title}", 
                           instance=instance, 
                           change_logs=change_logs) # Pass values_dict and file_urls if using them


@app.route("/experiments/<int:instance_id>/delete", methods=['POST'])
@login_required
def delete_experiment_instance(instance_id):
    instance = ExperimentInstance.query.get_or_404(instance_id)
    if instance.author != current_user and not current_user.is_admin: # Basic permission check
        flash('You do not have permission to delete this experiment.', 'danger')
        return redirect(url_for('list_experiments'))
    
    # Manually delete associated files if any (cascade delete won't handle filesystem)
    for fv in instance.field_values:
        if fv.field_definition_ref.field_type == 'FILE' and fv.value:
            try:
                # Assuming fv.value is path relative to UPLOAD_FOLDER root
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], fv.value)
                if os.path.exists(file_path):
                    # Also remove parent dirs if they become empty
                    os.remove(file_path)
                    # Clean up directories carefully: os.removedirs might be too aggressive
                    # For now, just remove the file. Directory cleanup can be a separate task.
            except Exception as e:
                app.logger.error(f"Error deleting file {fv.value} for experiment {instance.id}: {e}")

    db.session.delete(instance) # Cascade delete should handle DB children
    db.session.commit()
    flash('Experiment instance and associated data deleted successfully.', 'success')
    return redirect(url_for('list_experiments'))


# AJAX route to get patterns for a selected format (optional, for better UX)
@app.route("/experiments/get_patterns/<int:format_id>")
@login_required
def get_patterns(format_id):
    patterns = FormatPattern.query.filter_by(experiment_format_id=format_id).all()
    pattern_list = [{"id": p.id, "name": p.name, "data": p.pattern_data} for p in patterns]
    return jsonify(patterns=pattern_list)

# AJAX route to get field definitions for a selected format (for dynamic form updates if needed)
@app.route("/experiments/get_format_fields/<int:format_id>")
@login_required
def get_format_fields(format_id):
    exp_format = ExperimentFormat.query.get_or_404(format_id)
    field_list = [
        {"id": f.id, "name": f.name, "type": f.field_type, "units": f.units, 
         "is_required": f.is_required, "options": f.dropdown_options} 
        for f in exp_format.fields
    ]
    return jsonify(fields=field_list)


# Plate Layout Management Routes
@app.route("/layouts")
@login_required
def list_plate_layouts():
    query = PlateLayout.query.filter_by(user_id=current_user.id) # Base query for current user
    
    search_term = request.args.get('search_term', '')
    layout_type_filter = request.args.get('layout_type_filter', '')

    if search_term:
        query = query.filter(
            or_(
                PlateLayout.name.ilike(f'%{search_term}%'),
                PlateLayout.description.ilike(f'%{search_term}%')
            )
        )
    if layout_type_filter:
        query = query.filter(PlateLayout.layout_type == layout_type_filter)
        
    layouts = query.order_by(PlateLayout.name).all()
    # Get choices for the filter dropdown from PlateLayoutForm
    layout_type_choices = PlateLayoutForm().layout_type.choices
    
    return render_template('layouts/list_layouts.html', 
                           layouts=layouts, title="Plate Layouts",
                           search_term=search_term, layout_type_filter=layout_type_filter,
                           layout_type_choices=layout_type_choices)

@app.route("/layouts/new", methods=['GET', 'POST'])
@login_required
def create_plate_layout():
    form = PlateLayoutForm()
    if form.validate_on_submit():
        plate_layout = PlateLayout(
            name=form.name.data,
            description=form.description.data,
            layout_type=form.layout_type.data,
            rows=form.rows.data if form.layout_type.data != 'CUSTOM_TUBES' else None,
            columns=form.columns.data if form.layout_type.data != 'CUSTOM_TUBES' else None,
            num_tubes=form.num_tubes.data if form.layout_type.data == 'CUSTOM_TUBES' else None,
            user_id=current_user.id
        )
        db.session.add(plate_layout)
        db.session.commit()
        flash('Plate layout created. You can now add custom well properties.', 'success')
        return redirect(url_for('edit_plate_layout', layout_id=plate_layout.id))
    # If form errors, they will be displayed by the template
    return render_template('layouts/create_edit_layout.html', title="Create Plate Layout", form=form, layout=None)


@app.route("/layouts/<int:layout_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_plate_layout(layout_id):
    layout = PlateLayout.query.get_or_404(layout_id)
    if layout.user_id != current_user.id:
        flash('You are not authorized to edit this layout.', 'danger')
        return redirect(url_for('list_plate_layouts'))

    form = PlateLayoutForm(obj=layout)
    # For adding new properties, we use a separate simple form instance.
    # Editing existing properties directly in a FieldList is complex without JS frameworks.
    # A common pattern is to list existing, allow delete, and have a form to add new.
    new_prop_form = WellPropertyDefinitionForm(prefix="new_prop") # Prefix to avoid name clashes

    if form.validate_on_submit() and request.form.get('submit_layout_details'):
        layout.name = form.name.data
        layout.description = form.description.data
        # Prevent changing layout_type, rows, columns, num_tubes after creation to maintain integrity
        # If change is needed, a new layout should be created.
        # This is because existing WellData might be based on current dimensions.
        # layout.layout_type = form.layout_type.data # Keep this disabled
        # layout.rows = form.rows.data if form.layout_type.data != 'CUSTOM_TUBES' else None
        # layout.columns = form.columns.data if form.layout_type.data != 'CUSTOM_TUBES' else None
        # layout.num_tubes = form.num_tubes.data if form.layout_type.data == 'CUSTOM_TUBES' else None
        db.session.commit()
        flash('Plate layout details updated.', 'success')
        return redirect(url_for('edit_plate_layout', layout_id=layout.id))
    
    # Handle adding a new property definition
    if new_prop_form.validate_on_submit() and request.form.get('add_property'):
        prop = WellPropertyDefinition(
            plate_layout_id=layout.id,
            property_name=new_prop_form.property_name.data,
            property_type=new_prop_form.property_type.data
        )
        db.session.add(prop)
        db.session.commit()
        flash('Well property definition added.', 'success')
        return redirect(url_for('edit_plate_layout', layout_id=layout.id))

    return render_template('layouts/create_edit_layout.html', title=f"Edit: {layout.name}", 
                           form=form, layout=layout, new_prop_form=new_prop_form)


@app.route("/layouts/<int:layout_id>")
@login_required
def view_plate_layout(layout_id):
    layout = PlateLayout.query.get_or_404(layout_id)
    if layout.user_id != current_user.id: # Basic permission
         flash('You are not authorized to view this layout.', 'danger')
         return redirect(url_for('list_plate_layouts'))
    return render_template('layouts/view_layout.html', layout=layout, title=f"View: {layout.name}")


@app.route("/layouts/<int:layout_id>/delete", methods=['POST'])
@login_required
def delete_plate_layout(layout_id):
    layout = PlateLayout.query.get_or_404(layout_id)
    if layout.user_id != current_user.id:
        flash('You are not authorized to delete this layout.', 'danger')
        return redirect(url_for('list_plate_layouts'))
    
    if layout.experiment_links: # Check if layout is currently linked to any experiments
        flash('This plate layout is linked to one or more experiments and cannot be deleted. Please unlink it from experiments first.', 'danger')
        return redirect(url_for('list_plate_layouts'))
    
    # Cascade delete should handle WellPropertyDefinitions
    db.session.delete(layout)
    db.session.commit()
    flash('Plate layout and its property definitions deleted.', 'success')
    return redirect(url_for('list_plate_layouts'))

@app.route("/layouts/property/<int:property_id>/delete", methods=['POST'])
@login_required
def delete_well_property_definition(property_id):
    prop_def = WellPropertyDefinition.query.get_or_404(property_id)
    layout = prop_def.plate_layout
    if layout.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('list_plate_layouts')) 

    data_exists_for_property = False
    for link in layout.experiment_links:
        for well in link.well_data:
            if well.custom_properties and prop_def.property_name in well.custom_properties:
                data_exists_for_property = True
                break
        if data_exists_for_property:
            break
            
    if data_exists_for_property:
        flash(f'Property "{prop_def.property_name}" has data recorded in experiments using this layout and cannot be deleted.', 'danger')
        return redirect(url_for('edit_plate_layout', layout_id=layout.id))

    db.session.delete(prop_def)
    db.session.commit()
    flash('Well property definition deleted.', 'success')
    return redirect(url_for('edit_plate_layout', layout_id=layout.id))


# Routes for Linking Plates to Experiments and Managing Well Data

@app.route("/experiments/<int:instance_id>/layouts/add", methods=['GET', 'POST'])
@login_required
def link_plate_to_experiment(instance_id):
    experiment = ExperimentInstance.query.get_or_404(instance_id)
    if experiment.author != current_user: # Basic permission check
        flash('You are not authorized to modify this experiment.', 'danger')
        return redirect(url_for('view_experiment_instance', instance_id=instance_id))

    form = LinkPlateToExperimentForm()
    # Ensure the query_factory for plate_layout only shows layouts by the current user or shared layouts (if that feature is added)
    form.plate_layout.query = PlateLayout.query.filter_by(user_id=current_user.id).order_by(PlateLayout.name).all()


    if form.validate_on_submit():
        # Check for unique name_in_experiment for this experiment
        existing_link = ExperimentPlateLink.query.filter_by(
            experiment_instance_id=instance_id,
            name_in_experiment=form.name_in_experiment.data
        ).first()
        if existing_link:
            flash('A plate/layout with this name already exists in this experiment. Please choose a unique name.', 'danger')
        else:
            plate_link = ExperimentPlateLink(
                experiment_instance_id=instance_id,
                plate_layout_id=form.plate_layout.data.id,
                name_in_experiment=form.name_in_experiment.data
            )
            db.session.add(plate_link)
            # Log this change
            log_experiment_change(instance_id, current_user.id, "Experiment Plate Layout", None, f"Linked: {plate_link.name_in_experiment} (Layout: {form.plate_layout.data.name})")
            db.session.commit()
            flash(f'Plate layout "{form.plate_layout.data.name}" linked as "{plate_link.name_in_experiment}". You can now enter well data.', 'success')
            return redirect(url_for('edit_well_data', instance_id=instance_id, link_id=plate_link.id))
    
    return render_template('experiments/link_plate_to_experiment.html', 
                           title="Link Plate Layout to Experiment", 
                           form=form, experiment=experiment)


@app.route("/experiments/<int:instance_id>/layout_links/<int:link_id>/data", methods=['GET', 'POST'])
@login_required
def edit_well_data(instance_id, link_id):
    plate_link = ExperimentPlateLink.query.get_or_404(link_id)
    experiment = plate_link.experiment_instance
    if experiment.author != current_user:
        flash('You are not authorized to edit data for this experiment.', 'danger')
        return redirect(url_for('view_experiment_instance', instance_id=instance_id))

    plate_layout = plate_link.plate_layout

    # Prepare existing well data for the form
    # Format: {well_identifier: {prop_name: value}}
    existing_well_data_map = {}
    for wd in plate_link.well_data:
        existing_well_data_map[wd.well_identifier] = wd.custom_properties if wd.custom_properties else {}

    form = generate_well_data_form(plate_link, data=request.form if request.method == 'POST' else None, existing_well_data=existing_well_data_map)

    if form.validate_on_submit():
        # Iterate through the dynamic fields in the form
        well_identifiers = []
        if plate_layout.layout_type != 'CUSTOM_TUBES':
            for r_idx in range(plate_layout.rows):
                row_char = chr(ord('A') + r_idx)
                for c_idx in range(plate_layout.columns):
                    well_identifiers.append(f"{row_char}{c_idx + 1}")
        else:
            for i in range(plate_layout.num_tubes):
                well_identifiers.append(f"Tube_{i + 1}")
        
        changes_made_summary = []

        for well_id_str in well_identifiers:
            well_custom_props_data = {}
            changed_in_this_well = False
            for prop_def in plate_layout.custom_property_definitions:
                form_field_name = f"well_{well_id_str}_prop_{prop_def.id}"
                submitted_value_obj = getattr(form, form_field_name, None)
                if submitted_value_obj:
                    submitted_value = submitted_value_obj.data
                    # For BooleanField, WTForms gives True/False. Convert to string if storing as string.
                    # Or handle specific types before storing in JSON.
                    if isinstance(submitted_value, bool):
                        submitted_value = str(submitted_value)
                    
                    if submitted_value is not None and submitted_value != '': # Only store if data is provided
                        well_custom_props_data[prop_def.property_name] = submitted_value
            
            # Get existing WellData or create new
            well_data_obj = WellData.query.filter_by(
                experiment_plate_link_id=link_id,
                well_identifier=well_id_str
            ).first()
            
            old_props_json = None
            if well_data_obj:
                old_props_json = json.dumps(well_data_obj.custom_properties) if well_data_obj.custom_properties else "{}"
                if well_custom_props_data: # If there's new data to save
                    if well_data_obj.custom_properties != well_custom_props_data:
                        well_data_obj.custom_properties = well_custom_props_data
                        changed_in_this_well = True
                elif well_data_obj.custom_properties: # New data is empty, but old data existed (clear it)
                    well_data_obj.custom_properties = None # Or {}
                    changed_in_this_well = True
            elif well_custom_props_data: # No existing WellData, but new data provided
                well_data_obj = WellData(
                    experiment_plate_link_id=link_id,
                    well_identifier=well_id_str,
                    custom_properties=well_custom_props_data
                )
                db.session.add(well_data_obj)
                changed_in_this_well = True
            
            if changed_in_this_well:
                new_props_json = json.dumps(well_custom_props_data) if well_custom_props_data else "{}"
                # Log change for this specific well
                log_experiment_change(instance_id, current_user.id, 
                                      f"Well Data: {plate_link.name_in_experiment} - {well_id_str}", 
                                      old_props_json, new_props_json)
                changes_made_summary.append(well_id_str)

        if changes_made_summary:
            experiment.last_modified_date = datetime.utcnow()
            db.session.commit()
            flash(f'Well data updated for wells: {", ".join(changes_made_summary[:5])}{"..." if len(changes_made_summary) > 5 else ""}.', 'success')
        else:
            flash('No changes detected in well data.', 'info')
            
        return redirect(url_for('edit_well_data', instance_id=instance_id, link_id=link_id))

    return render_template('experiments/edit_well_data.html', 
                           title=f"Edit Well Data for {plate_link.name_in_experiment}",
                           form=form, 
                           experiment=experiment, 
                           plate_link=plate_link, 
                           plate_layout=plate_layout)


# --- Experiment Scheme (Workflow) Management Routes ---

@app.route("/schemes")
@login_required
def list_schemes():
    query = ExperimentScheme.query.filter_by(user_id=current_user.id)
    search_term = request.args.get('search_term', '')

    if search_term:
        query = query.filter(
            or_(
                ExperimentScheme.name.ilike(f'%{search_term}%'),
                ExperimentScheme.description.ilike(f'%{search_term}%')
            )
        )
    
    schemes = query.order_by(ExperimentScheme.name).all()
    return render_template('schemes/list_schemes.html', 
                           schemes=schemes, title="Experiment Schemes",
                           search_term=search_term)

@app.route("/schemes/new", methods=['GET', 'POST'])
@login_required
def create_scheme():
    form = ExperimentSchemeForm() # Assuming ExperimentSchemeForm is imported
    if form.validate_on_submit():
        scheme = ExperimentScheme(
            name=form.name.data,
            description=form.description.data,
            user_id=current_user.id
        )
        db.session.add(scheme)
        db.session.commit()
        flash('Experiment scheme created. You can now design it.', 'success')
        return redirect(url_for('edit_scheme', scheme_id=scheme.id))
    return render_template('schemes/create_scheme.html', title="Create New Experiment Scheme", form=form)

@app.route("/schemes/<int:scheme_id>/edit", methods=['GET'])
@login_required
def edit_scheme(scheme_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id:
        flash('You are not authorized to edit this scheme.', 'danger')
        return redirect(url_for('list_schemes'))
    
    node_form = SchemeNodeForm() # Assuming SchemeNodeForm is imported
    
    nodes = [node.to_dict() for node in scheme.nodes.all()]
    edges = [edge.to_dict() for edge in scheme.edges.all()]
    
    return render_template('schemes/edit_scheme.html', title=f"Edit Scheme: {scheme.name}", 
                           scheme=scheme, node_form=node_form, nodes_json=json.dumps(nodes), edges_json=json.dumps(edges))

@app.route("/schemes/<int:scheme_id>/view", methods=['GET'])
@login_required
def view_scheme(scheme_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id: 
        flash('You are not authorized to view this scheme.', 'danger')
        return redirect(url_for('list_schemes'))
    
    nodes = [node.to_dict() for node in scheme.nodes.all()]
    edges = [edge.to_dict() for edge in scheme.edges.all()]
    
    return render_template('schemes/view_scheme.html', title=f"View Scheme: {scheme.name}",
                           scheme=scheme, nodes_json=json.dumps(nodes), edges_json=json.dumps(edges))


@app.route("/schemes/<int:scheme_id>/delete", methods=['POST'])
@login_required
def delete_scheme(scheme_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id:
        flash('You are not authorized to delete this scheme.', 'danger')
        return redirect(url_for('list_schemes'))
    
    db.session.delete(scheme)
    db.session.commit()
    flash('Experiment scheme and all its components deleted.', 'success')
    return redirect(url_for('list_schemes'))

# --- API Endpoints for Scheme Nodes & Edges ---

@app.route("/schemes/<int:scheme_id>/nodes", methods=['POST'])
@login_required
def add_scheme_node(scheme_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id:
        return jsonify(error="Unauthorized"), 403

    data = request.get_json()
    if not data or not data.get('label'):
        return jsonify(error="Label is required for a node."), 400
    
    linked_instance_id = data.get('linked_experiment_instance_id')
    if linked_instance_id:
        linked_instance = ExperimentInstance.query.get(linked_instance_id)
        if not linked_instance or linked_instance.user_id != current_user.id:
             return jsonify(error="Invalid or unauthorized experiment instance link."), 400
    
    linked_format_id = data.get('linked_experiment_format_id')
    if linked_format_id:
        linked_format = ExperimentFormat.query.get(linked_format_id)
        if not linked_format: # Add more checks if formats become user-specific
             return jsonify(error="Invalid experiment format link."), 400
    
    node = SchemeNode(
        scheme_id=scheme_id,
        label=data.get('label'),
        description=data.get('description'),
        pos_x=float(data.get('pos_x', 50)),
        pos_y=float(data.get('pos_y', 50)),
        width=float(data.get('width', 150)),
        height=float(data.get('height', 100)),
        color=data.get('color', '#FFFFFF'),
        linked_experiment_instance_id=linked_instance_id,
        linked_experiment_format_id=linked_format_id
    )
    db.session.add(node)
    db.session.commit()
    return jsonify(message="Node added", node=node.to_dict()), 201


@app.route("/schemes/<int:scheme_id>/nodes/<int:node_id>", methods=['PUT'])
@login_required
def update_scheme_node(scheme_id, node_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id: return jsonify(error="Unauthorized"), 403
    
    node = SchemeNode.query.get_or_404(node_id)
    if node.scheme_id != scheme_id: return jsonify(error="Node not found in this scheme"), 404

    data = request.get_json()
    if not data: return jsonify(error="No data provided for update."), 400

    if 'label' in data: node.label = data['label']
    if 'description' in data: node.description = data['description']
    if 'pos_x' in data: node.pos_x = float(data['pos_x'])
    if 'pos_y' in data: node.pos_y = float(data['pos_y'])
    if 'width' in data: node.width = float(data['width'])
    if 'height' in data: node.height = float(data['height'])
    if 'color' in data: node.color = data['color']
    
    if 'linked_experiment_instance_id' in data:
        instance_id = data['linked_experiment_instance_id']
        if instance_id: # If an ID is provided
            linked_instance = ExperimentInstance.query.get(instance_id)
            if not linked_instance or linked_instance.user_id != current_user.id:
                return jsonify(error="Invalid or unauthorized experiment instance link."), 400
            node.linked_experiment_instance_id = linked_instance.id
        else: # If null or empty string is passed to clear the link
            node.linked_experiment_instance_id = None

    if 'linked_experiment_format_id' in data:
        format_id = data['linked_experiment_format_id']
        if format_id:
            linked_format = ExperimentFormat.query.get(format_id)
            if not linked_format: # Add more checks if formats become user-specific
                 return jsonify(error="Invalid experiment format link."), 400
            node.linked_experiment_format_id = linked_format.id
        else:
            node.linked_experiment_format_id = None
            
    db.session.commit()
    return jsonify(message="Node updated", node=node.to_dict())


@app.route("/schemes/<int:scheme_id>/nodes/<int:node_id>", methods=['DELETE'])
@login_required
def delete_scheme_node(scheme_id, node_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id: return jsonify(error="Unauthorized"), 403
    
    node = SchemeNode.query.get_or_404(node_id)
    if node.scheme_id != scheme_id: return jsonify(error="Node not found in this scheme"), 404

    db.session.delete(node)
    db.session.commit()
    return jsonify(message="Node deleted")


@app.route("/schemes/<int:scheme_id>/edges", methods=['POST'])
@login_required
def add_scheme_edge(scheme_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id: return jsonify(error="Unauthorized"), 403

    data = request.get_json()
    if not data or 'source_node_id' not in data or 'target_node_id' not in data:
        return jsonify(error="Source and target node IDs are required."), 400

    source_node = SchemeNode.query.filter_by(id=data['source_node_id'], scheme_id=scheme_id).first()
    target_node = SchemeNode.query.filter_by(id=data['target_node_id'], scheme_id=scheme_id).first()

    if not source_node or not target_node:
        return jsonify(error="Source or target node not found in this scheme."), 404
    
    existing_edge = SchemeEdge.query.filter_by(
        scheme_id=scheme_id,
        source_node_id=data['source_node_id'],
        target_node_id=data['target_node_id']
    ).first()
    if existing_edge:
        return jsonify(error="Edge already exists.", edge=existing_edge.to_dict()), 409

    edge = SchemeEdge(
        scheme_id=scheme_id,
        source_node_id=data['source_node_id'],
        target_node_id=data['target_node_id'],
        label=data.get('label')
    )
    db.session.add(edge)
    db.session.commit()
    return jsonify(message="Edge added", edge=edge.to_dict()), 201


@app.route("/schemes/<int:scheme_id>/edges/<int:edge_id>", methods=['DELETE'])
@login_required
def delete_scheme_edge(scheme_id, edge_id):
    scheme = ExperimentScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id: return jsonify(error="Unauthorized"), 403

    edge = SchemeEdge.query.get_or_404(edge_id)
    if edge.scheme_id != scheme_id: return jsonify(error="Edge not found in this scheme"), 404
        
    db.session.delete(edge)
    db.session.commit()
    return jsonify(message="Edge deleted")

# --- Data Export Routes ---

def set_cell_style(cell, bold=False, alignment=None, fill=None, border=None, font_size=11):
    cell.font = Font(bold=bold, size=font_size)
    if alignment:
        cell.alignment = alignment
    if fill:
        cell.fill = fill
    if border:
        cell.border = border

@app.route("/experiments/<int:instance_id>/export/excel")
@login_required
def export_experiment_excel(instance_id):
    experiment = ExperimentInstance.query.get_or_404(instance_id)
    # Optional: Add permission check if current_user can view/export this experiment

    wb = openpyxl.Workbook()
    
    # --- Sheet 1: Experiment Details & Field Values ---
    ws_details = wb.active
    ws_details.title = "Experiment Details"

    # Styles
    header_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
    bold_font = Font(bold=True, size=12)
    section_header_font = Font(bold=True, size=14)
    thin_border_side = Side(border_style="thin", color="000000")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    ws_details.cell(row=1, column=1, value="Experiment Details").font = section_header_font
    
    details_data = [
        ("Title:", experiment.title),
        ("Experiment Date:", experiment.experiment_date.strftime('%Y-%m-%d') if experiment.experiment_date else "N/A"),
        ("Status:", experiment.status),
        ("Created By:", experiment.author.username),
        ("Creation Date:", experiment.creation_date.strftime('%Y-%m-%d %H:%M:%S UTC')),
        ("Last Modified:", experiment.last_modified_date.strftime('%Y-%m-%d %H:%M:%S UTC')),
        ("Experiment Format:", experiment.experiment_format_ref.name),
    ]

    row_idx = 2
    for label, value in details_data:
        ws_details.cell(row=row_idx, column=1, value=label).font = bold_font
        ws_details.cell(row=row_idx, column=2, value=value)
        row_idx += 1
    
    row_idx += 1 # Spacer
    ws_details.cell(row=row_idx, column=1, value="Field Values").font = section_header_font
    row_idx += 1
    
    field_headers = ["Field Name", "Value", "Units", "Required"]
    for col_idx, header_title in enumerate(field_headers, 1):
        cell = ws_details.cell(row=row_idx, column=col_idx, value=header_title)
        set_cell_style(cell, bold=True, fill=header_fill, border=thin_border)
    row_idx += 1

    for fv in sorted(experiment.field_values, key=lambda x: x.field_definition_ref.id):
        field_def = fv.field_definition_ref
        ws_details.cell(row=row_idx, column=1, value=field_def.name).border = thin_border
        # Handle file paths for linked files - make them clickable if possible (or just show path)
        if field_def.field_type == 'FILE' and fv.value:
             # Assuming fv.value is relative path from UPLOAD_FOLDER
             # This won't make it a clickable link directly to local file system for security reasons
             # but provides the path. For web URLs, Hyperlink can be used.
            ws_details.cell(row=row_idx, column=2, value=fv.value).border = thin_border
            # cell.hyperlink = fv.value # If it were a URL
        else:
            ws_details.cell(row=row_idx, column=2, value=fv.value).border = thin_border
        ws_details.cell(row=row_idx, column=3, value=field_def.units or "").border = thin_border
        ws_details.cell(row=row_idx, column=4, value="Yes" if field_def.is_required else "No").border = thin_border
        row_idx += 1

    # Auto-adjust column widths for details sheet
    for col in ws_details.columns:
        max_length = 0
        column = col[0].column_letter # Get the column name
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws_details.column_dimensions[column].width = adjusted_width


    # --- Sheet per Linked Plate ---
    for plate_link in experiment.plate_links:
        ws_plate = wb.create_sheet(title=plate_link.name_in_experiment[:31]) # Sheet title limit
        plate_layout = plate_link.plate_layout
        
        ws_plate.cell(row=1, column=1, value=f"Plate Data: {plate_link.name_in_experiment}").font = section_header_font
        ws_plate.cell(row=2, column=1, value=f"Layout Template: {plate_layout.name} ({plate_layout.layout_type.replace('_',' ')})").font = bold_font
        row_idx = 4

        prop_defs = list(plate_layout.custom_property_definitions) # Ordered list of properties
        prop_names = [pd.property_name for pd in prop_defs]

        if plate_layout.layout_type != 'CUSTOM_TUBES' and plate_layout.rows and plate_layout.columns:
            # Grid layout
            header_row = ["Well"] + prop_names
            for col_idx, header_title in enumerate(header_row, 1):
                cell = ws_plate.cell(row=row_idx, column=col_idx, value=header_title)
                set_cell_style(cell, bold=True, fill=header_fill, border=thin_border)
            row_idx += 1

            for r in range(plate_layout.rows):
                row_char = chr(ord('A') + r)
                for c in range(plate_layout.columns):
                    well_id_str = f"{row_char}{c + 1}"
                    ws_plate.cell(row=row_idx, column=1, value=well_id_str).border = thin_border
                    
                    well_data_entry = WellData.query.filter_by(experiment_plate_link_id=plate_link.id, well_identifier=well_id_str).first()
                    well_props = well_data_entry.custom_properties if well_data_entry and well_data_entry.custom_properties else {}
                    
                    for col_idx_offset, prop_name in enumerate(prop_names):
                        ws_plate.cell(row=row_idx, column=2 + col_idx_offset, value=well_props.get(prop_name, "")).border = thin_border
                    row_idx += 1
        else: # Custom tubes layout
            header_row = ["Tube Identifier"] + prop_names
            for col_idx, header_title in enumerate(header_row, 1):
                cell = ws_plate.cell(row=row_idx, column=col_idx, value=header_title)
                set_cell_style(cell, bold=True, fill=header_fill, border=thin_border)
            row_idx += 1

            for i in range(plate_layout.num_tubes or 0):
                tube_id_str = f"Tube_{i + 1}"
                ws_plate.cell(row=row_idx, column=1, value=tube_id_str).border = thin_border
                
                well_data_entry = WellData.query.filter_by(experiment_plate_link_id=plate_link.id, well_identifier=tube_id_str).first()
                well_props = well_data_entry.custom_properties if well_data_entry and well_data_entry.custom_properties else {}

                for col_idx_offset, prop_name in enumerate(prop_names):
                    ws_plate.cell(row=row_idx, column=2 + col_idx_offset, value=well_props.get(prop_name, "")).border = thin_border
                row_idx += 1
        
        # Auto-adjust column widths for plate sheet
        for col in ws_plate.columns:
            max_length = 0
            column = col[0].column_letter
            for cell_obj in col: # Renamed cell to cell_obj to avoid conflict
                try:
                    if len(str(cell_obj.value)) > max_length:
                        max_length = len(str(cell_obj.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws_plate.column_dimensions[column].width = adjusted_width

    # --- (Optional) Sheet for Change Logs ---
    ws_logs = wb.create_sheet(title="Change Log")
    ws_logs.cell(row=1, column=1, value="Experiment Change Log").font = section_header_font
    log_headers = ["Timestamp", "User", "Field Name", "Old Value", "New Value"]
    row_idx = 2
    for col_idx, header_title in enumerate(log_headers, 1):
        cell = ws_logs.cell(row=row_idx, column=col_idx, value=header_title)
        set_cell_style(cell, bold=True, fill=header_fill, border=thin_border)
    row_idx += 1

    for log_entry in sorted(experiment.change_logs, key=lambda x: x.timestamp, reverse=True):
        ws_logs.cell(row=row_idx, column=1, value=log_entry.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')).border = thin_border
        ws_logs.cell(row=row_idx, column=2, value=log_entry.user.username).border = thin_border
        ws_logs.cell(row=row_idx, column=3, value=log_entry.field_name).border = thin_border
        ws_logs.cell(row=row_idx, column=4, value=log_entry.old_value).border = thin_border
        ws_logs.cell(row=row_idx, column=5, value=log_entry.new_value).border = thin_border
        row_idx += 1
    
    for col in ws_logs.columns:
        max_length = 0
        column = col[0].column_letter
        for cell_obj in col:
            try:
                if len(str(cell_obj.value)) > max_length:
                    max_length = len(str(cell_obj.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws_logs.column_dimensions[column].width = adjusted_width

    # Save to BytesIO stream
    excel_stream = BytesIO()
    wb.save(excel_stream)
    excel_stream.seek(0) # Go to the beginning of the stream

    safe_title = secure_filename(experiment.title)
    filename = f"experiment_{safe_title}_{experiment.id}.xlsx"
    
    return send_file(
        excel_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route("/experiments/<int:instance_id>/export/pdf")
@login_required
def export_experiment_pdf(instance_id):
    experiment = ExperimentInstance.query.get_or_404(instance_id)
    # Optional: Permission check

    # Render the HTML template with experiment data
    html_out = render_template('exports/export_experiment.html', experiment=experiment)
    
    # Use xhtml2pdf to convert HTML to PDF
    pdf_stream = BytesIO()
    pdf = pisa.CreatePDF(html_out, dest=pdf_stream)
    if pdf.err:
        current_app.logger.error(f"PDF generation error: {pdf.err}")
        raise Exception(f"PDF generation error: {pdf.err}")
    pdf_stream.seek(0)

    safe_title = secure_filename(experiment.title)
    filename = f"experiment_{safe_title}_{experiment.id}.pdf"

    return send_file(
        pdf_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


@app.route("/experiments/<int:instance_id>/layout_links/<int:link_id>/unlink", methods=['POST'])
@login_required
def unlink_plate_from_experiment(instance_id, link_id):
    plate_link = ExperimentPlateLink.query.get_or_404(link_id)
    experiment = plate_link.experiment_instance

    if experiment.author != current_user: # Basic permission check
        flash('You are not authorized to modify this experiment.', 'danger')
        return redirect(url_for('view_experiment_instance', instance_id=instance_id))

    if plate_link.experiment_instance_id != instance_id: # Ensure link belongs to the experiment in URL
        flash('Invalid operation: Plate link does not belong to this experiment.', 'danger')
        return redirect(url_for('view_experiment_instance', instance_id=instance_id))

    layout_name = plate_link.plate_layout.name
    name_in_exp = plate_link.name_in_experiment
    
    db.session.delete(plate_link)
    log_experiment_change(instance_id, current_user.id, "Experiment Plate Layout", f"Unlinked: {name_in_exp} (Layout: {layout_name})", None)
    experiment.last_modified_date = datetime.utcnow()
    db.session.commit()

    flash(f'Plate layout "{name_in_exp}" and its data have been unlinked from this experiment.', 'success')
    return redirect(url_for('view_experiment_instance', instance_id=instance_id))
