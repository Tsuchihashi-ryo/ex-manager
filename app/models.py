from app import db, app # Added app import for app_context
from sqlalchemy.dialects.postgresql import JSON as PG_JSON # If using PostgreSQL for JSON
from sqlalchemy import JSON as SQLA_JSON # For SQLite or other DBs supporting JSON
from datetime import datetime, date 

# Helper to choose JSON type based on DB dialect
JSON_TYPE = PG_JSON if db.engine.dialect.name == 'postgresql' else SQLA_JSON


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password = db.Column(db.String(60), nullable=False)
    experiments = db.relationship('ExperimentInstance', backref='author', lazy=True)
    change_logs = db.relationship('ExperimentChangeLog', backref='user', lazy=True)
    plate_layouts = db.relationship('PlateLayout', backref='creator', lazy=True)


    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.image_file}')"

class ExperimentFormat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    fields = db.relationship('FieldDefinition', backref='experiment_format', lazy=True, cascade="all, delete-orphan")
    patterns = db.relationship('FormatPattern', backref='experiment_format', lazy=True, cascade="all, delete-orphan")
    instances = db.relationship('ExperimentInstance', backref='experiment_format_ref', lazy=True)


    def __repr__(self):
        return f"ExperimentFormat('{self.name}')"

class FieldDefinition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    field_type = db.Column(db.String(50), nullable=False)
    units = db.Column(db.String(50), nullable=True) 
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    dropdown_options = db.Column(db.Text, nullable=True) 
    experiment_format_id = db.Column(db.Integer, db.ForeignKey('experiment_format.id'), nullable=False)
    values = db.relationship('ExperimentFieldValue', backref='field_definition_ref', lazy=True)


    def __repr__(self):
        return f"FieldDefinition('{self.name}', '{self.field_type}')"

class FormatPattern(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    experiment_format_id = db.Column(db.Integer, db.ForeignKey('experiment_format.id'), nullable=False)
    pattern_data = db.Column(JSON_TYPE, nullable=True) 

    def __repr__(self):
        return f"FormatPattern('{self.name}', Format: '{self.experiment_format.name}')"


class ExperimentInstance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    creation_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_modified_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    experiment_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="DRAFT")
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    format_id = db.Column(db.Integer, db.ForeignKey('experiment_format.id'), nullable=False)
    
    field_values = db.relationship('ExperimentFieldValue', backref='experiment_instance', lazy=True, cascade="all, delete-orphan")
    change_logs = db.relationship('ExperimentChangeLog', backref='experiment_instance', lazy=True, cascade="all, delete-orphan")
    plate_links = db.relationship('ExperimentPlateLink', backref='experiment_instance', lazy=True, cascade="all, delete-orphan")


    def __repr__(self):
        return f"ExperimentInstance('{self.title}', Status: '{self.status}', Author: '{self.author.username}')"

class ExperimentFieldValue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    experiment_instance_id = db.Column(db.Integer, db.ForeignKey('experiment_instance.id'), nullable=False)
    field_definition_id = db.Column(db.Integer, db.ForeignKey('field_definition.id'), nullable=False)
    value = db.Column(db.Text, nullable=True) 

    def __repr__(self):
        with app.app_context(): 
             return f"FieldValue(Instance: '{self.experiment_instance.title}', Field: '{self.field_definition_ref.name}', Value: '{self.value[:30]}...')"


class ExperimentChangeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    experiment_instance_id = db.Column(db.Integer, db.ForeignKey('experiment_instance.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
    field_name = db.Column(db.String(100), nullable=False) 
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)

    def __repr__(self):
        with app.app_context(): 
            return f"ChangeLog(Instance: '{self.experiment_instance.title}', Field: '{self.field_name}', User: '{self.user.username}')"

# New Models for Plate Layout Management

class PlateLayout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    layout_type = db.Column(db.String(50), nullable=False) # E.g., "PLATE_96", "PLATE_384", "CUSTOM_TUBES"
    rows = db.Column(db.Integer, nullable=True)
    columns = db.Column(db.Integer, nullable=True)
    num_tubes = db.Column(db.Integer, nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Creator
    
    custom_property_definitions = db.relationship('WellPropertyDefinition', backref='plate_layout', lazy=True, cascade="all, delete-orphan")
    # This relationship might be complex if a layout is a template vs. instance specific
    # For now, assuming a layout can be linked to multiple experiments (as a template)
    experiment_links = db.relationship('ExperimentPlateLink', backref='plate_layout', lazy=True)


    def __repr__(self):
        return f"PlateLayout('{self.name}', Type: '{self.layout_type}')"

class WellPropertyDefinition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_layout_id = db.Column(db.Integer, db.ForeignKey('plate_layout.id'), nullable=False)
    property_name = db.Column(db.String(100), nullable=False)
    property_type = db.Column(db.String(50), nullable=False, default="TEXT") # E.g., "TEXT", "NUMBER", "BOOLEAN"

    def __repr__(self):
        return f"WellPropertyDefinition('{self.property_name}', Type: '{self.property_type}')"

class ExperimentPlateLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    experiment_instance_id = db.Column(db.Integer, db.ForeignKey('experiment_instance.id'), nullable=False)
    plate_layout_id = db.Column(db.Integer, db.ForeignKey('plate_layout.id'), nullable=False)
    name_in_experiment = db.Column(db.String(100), nullable=False) # E.g., "Input Plate 1", "Reagent Tubes A"
    
    well_data = db.relationship('WellData', backref='experiment_plate_link', lazy=True, cascade="all, delete-orphan")

    # Unique constraint for name_in_experiment within the same experiment instance
    __table_args__ = (db.UniqueConstraint('experiment_instance_id', 'name_in_experiment', name='_exp_plate_name_uc'),)

    def __repr__(self):
        return f"ExperimentPlateLink(Exp: '{self.experiment_instance.title}', Layout: '{self.plate_layout.name}', Name: '{self.name_in_experiment}')"

class WellData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    experiment_plate_link_id = db.Column(db.Integer, db.ForeignKey('experiment_plate_link.id'), nullable=False)
    well_identifier = db.Column(db.String(50), nullable=False) # E.g., "A1", "H12", "Tube_1", "Position_5"
    custom_properties = db.Column(JSON_TYPE, nullable=True) # Stores key-value pairs, e.g., {"Sample ID": "S101"}

    # Unique constraint for well_identifier within the same plate link
    __table_args__ = (db.UniqueConstraint('experiment_plate_link_id', 'well_identifier', name='_plate_link_well_uc'),)

    def __repr__(self):
        return f"WellData(Link: '{self.experiment_plate_link.name_in_experiment}', Well: '{self.well_identifier}')"

# New Models for Experiment Scheme (Workflow) Management

class ExperimentScheme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    nodes = db.relationship('SchemeNode', backref='scheme', lazy='dynamic', cascade="all, delete-orphan")
    edges = db.relationship('SchemeEdge', backref='scheme', lazy='dynamic', cascade="all, delete-orphan")
    
    creator = db.relationship('User', backref='schemes') # Define the backref for User.schemes

    def __repr__(self):
        return f"ExperimentScheme('{self.name}', User: '{self.creator.username}')"

class SchemeNode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scheme_id = db.Column(db.Integer, db.ForeignKey('experiment_scheme.id'), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    pos_x = db.Column(db.Float, default=50.0)
    pos_y = db.Column(db.Float, default=50.0)
    width = db.Column(db.Float, default=150.0) # Default width
    height = db.Column(db.Float, default=100.0) # Default height
    color = db.Column(db.String(50), default="#FFFFFF") # Default color (white)
    
    linked_experiment_instance_id = db.Column(db.Integer, db.ForeignKey('experiment_instance.id'), nullable=True)
    linked_experiment_format_id = db.Column(db.Integer, db.ForeignKey('experiment_format.id'), nullable=True)

    experiment_instance = db.relationship('ExperimentInstance', backref='scheme_nodes', lazy=True)
    experiment_format = db.relationship('ExperimentFormat', backref='scheme_nodes', lazy=True)

    # For edges
    outgoing_edges = db.relationship('SchemeEdge', foreign_keys='SchemeEdge.source_node_id', backref='source_node', lazy='dynamic', cascade="all, delete-orphan")
    incoming_edges = db.relationship('SchemeEdge', foreign_keys='SchemeEdge.target_node_id', backref='target_node', lazy='dynamic', cascade="all, delete-orphan")

    def to_dict(self): # Helper to convert node to dict for JSON API
        return {
            'id': self.id,
            'scheme_id': self.scheme_id,
            'label': self.label,
            'description': self.description,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'width': self.width,
            'height': self.height,
            'color': self.color,
            'linked_experiment_instance_id': self.linked_experiment_instance_id,
            'linked_experiment_format_id': self.linked_experiment_format_id,
            'linked_experiment_instance_name': self.experiment_instance.title if self.experiment_instance else None,
            'linked_experiment_format_name': self.experiment_format.name if self.experiment_format else None,
        }

    def __repr__(self):
        return f"SchemeNode('{self.label}', SchemeID: {self.scheme_id})"

class SchemeEdge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scheme_id = db.Column(db.Integer, db.ForeignKey('experiment_scheme.id'), nullable=False)
    source_node_id = db.Column(db.Integer, db.ForeignKey('scheme_node.id'), nullable=False)
    target_node_id = db.Column(db.Integer, db.ForeignKey('scheme_node.id'), nullable=False)
    label = db.Column(db.String(100), nullable=True)

    # Relationships already defined in SchemeNode via foreign_keys for source_node and target_node
    # scheme = db.relationship('ExperimentScheme', backref='edges') # Defined in ExperimentScheme

    def to_dict(self): # Helper to convert edge to dict for JSON API
        return {
            'id': self.id,
            'scheme_id': self.scheme_id,
            'source_node_id': self.source_node_id,
            'target_node_id': self.target_node_id,
            'label': self.label
        }

    def __repr__(self):
        return f"SchemeEdge(Source: {self.source_node_id} -> Target: {self.target_node_id}, SchemeID: {self.scheme_id})"
