from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, SelectField, FieldList, FormField, DateField, FileField, IntegerField, HiddenField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional, NumberRange
from wtforms.widgets import DateInput # For DateField
from flask_wtf.file import FileAllowed # For FileField
from app.models import User, ExperimentFormat, FormatPattern, PlateLayout # Import PlateLayout for QuerySelectField

# QuerySelectField needs a query_factory
from wtforms_sqlalchemy.fields import QuerySelectField


class RegistrationForm(FlaskForm):
    username = StringField('Username',
                           validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose a different one.')

class LoginForm(FlaskForm):
    username = StringField('Username',
                           validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

# Forms for Experiment Format Management (Existing - no changes here)

class FieldDefinitionForm(FlaskForm): 
    name = StringField('Field Name', validators=[DataRequired(), Length(max=100)])
    field_type = SelectField('Field Type', choices=[
        ('TEXT', 'Text'), ('NUMBER', 'Number'), ('DATE', 'Date'),
        ('DROPDOWN', 'Dropdown'), ('CHECKBOX', 'Checkbox'), ('FILE', 'File')
    ], validators=[DataRequired()])
    units = StringField('Units', validators=[Optional(), Length(max=50)])
    is_required = BooleanField('Required', default=True)
    dropdown_options = TextAreaField('Dropdown Options (comma-separated)', validators=[Optional()])

class ExperimentFormatForm(FlaskForm):
    name = StringField('Format Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    submit = SubmitField('Save Format')

class FormatPatternForm(FlaskForm):
    name = StringField('Pattern Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    pattern_data_json = TextAreaField('Pattern Data (JSON)', validators=[Optional()])
    submit = SubmitField('Save Pattern')


# Forms for Experiment Instance Management (Existing - no changes here)

def get_experiment_formats():
    return ExperimentFormat.query.all()

class CreateExperimentInstanceForm(FlaskForm):
    title = StringField('Experiment Title', validators=[DataRequired(), Length(max=200)])
    experiment_date = DateField('Experiment Date', validators=[DataRequired()], widget=DateInput())
    experiment_format = QuerySelectField('Experiment Format', 
                                         query_factory=get_experiment_formats, 
                                         get_label='name', 
                                         allow_blank=False,
                                         validators=[DataRequired()])
    status = SelectField('Status', choices=[
        ('DRAFT', 'Draft'), ('IN_PROGRESS', 'In Progress'), ('COMPLETED', 'Completed'),
        ('REVIEW', 'Under Review'), ('ANALYSIS', 'Data Analysis'), ('ARCHIVED', 'Archived')
    ], validators=[DataRequired()])
    submit = SubmitField('Proceed to Data Entry / Save Experiment')

class ExperimentInstanceDataEntryForm(FlaskForm): # Base class for dynamic form
    pattern_to_apply = SelectField('Apply Pattern (Optional)', choices=[], validators=[Optional()])
    submit_data = SubmitField('Save Data')

def generate_dynamic_data_form(experiment_format, data=None, existing_values=None):
    class DynamicForm(ExperimentInstanceDataEntryForm):
        pass
    pattern_choices = [('', '-- No Pattern --')] + [(str(p.id), p.name) for p in experiment_format.patterns]
    setattr(DynamicForm, 'pattern_to_apply', SelectField('Apply Pattern (Optional)', choices=pattern_choices, validators=[Optional()]))
    for field_def in experiment_format.fields:
        field_name = f"field_{field_def.id}"
        label = f"{field_def.name}" + (f" ({field_def.units})" if field_def.units else "")
        validators = [Optional()]
        if field_def.is_required: validators = [DataRequired()]
        current_value = existing_values.get(field_def.id) if existing_values else None
        if field_def.field_type == 'TEXT': field = StringField(label, validators=validators, default=current_value)
        elif field_def.field_type == 'NUMBER': field = StringField(label, validators=validators, default=current_value) # Keep as StringField for flexibility
        elif field_def.field_type == 'DATE': field = DateField(label, validators=validators, widget=DateInput(), default=current_value)
        elif field_def.field_type == 'DROPDOWN':
            choices = [(opt.strip(), opt.strip()) for opt in (field_def.dropdown_options or "").split(',') if opt.strip()]
            field = SelectField(label, choices=choices, validators=validators, default=current_value)
        elif field_def.field_type == 'CHECKBOX':
            bool_current_value = str(current_value).lower() == 'true'
            field = BooleanField(label, default=bool_current_value) # Removed validators for BooleanField as DataRequired is tricky
        elif field_def.field_type == 'FILE':
            field = FileField(label, validators=validators + [FileAllowed(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'csv', 'xls', 'xlsx', 'doc', 'docx'], 'Allowed file types only!')])
        else: field = StringField(label, validators=validators, default=current_value)
        setattr(DynamicForm, field_name, field)
    return DynamicForm(data) if data else DynamicForm()


# Forms for Plate Layout Management

class WellPropertyDefinitionForm(FlaskForm): # Used as FieldList(FormField(...))
    # id = HiddenField() # To track existing properties for updates/deletions
    property_name = StringField('Property Name', validators=[DataRequired(), Length(max=100)])
    property_type = SelectField('Property Type', choices=[
        ('TEXT', 'Text'), ('NUMBER', 'Number'), ('BOOLEAN', 'Boolean')
    ], validators=[DataRequired()])
    # submit = SubmitField('Save Property') # Not needed if part of parent form

class PlateLayoutForm(FlaskForm):
    name = StringField('Layout Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    layout_type = SelectField('Layout Type', choices=[
        ('PLATE_96', '96-well Plate (8x12)'),
        ('PLATE_384', '384-well Plate (16x24)'),
        # Add other standard plate types as needed
        ('CUSTOM_TUBES', 'Custom N Tubes/Wells')
    ], validators=[DataRequired()])
    
    # Fields for standard plate types (conditionally displayed via JS)
    rows = IntegerField('Rows', validators=[Optional(), NumberRange(min=1, max=100)]) # Max can be adjusted
    columns = IntegerField('Columns', validators=[Optional(), NumberRange(min=1, max=100)])
    
    # Field for custom tube type (conditionally displayed via JS)
    num_tubes = IntegerField('Number of Tubes/Wells', validators=[Optional(), NumberRange(min=1, max=1000)]) # Max can be adjusted

    # For adding/editing WellPropertyDefinitions
    custom_properties = FieldList(FormField(WellPropertyDefinitionForm), min_entries=0)
    
    submit = SubmitField('Save Layout')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        
        layout_type = self.layout_type.data
        if layout_type in ['PLATE_96', 'PLATE_384']:
            if not self.rows.data or not self.columns.data:
                msg = "Rows and Columns are required for standard plate types."
                self.rows.errors.append(msg)
                self.columns.errors.append(msg)
                return False
            if layout_type == 'PLATE_96' and (self.rows.data != 8 or self.columns.data != 12):
                msg = "96-well plate must be 8 rows by 12 columns."
                self.rows.errors.append(msg)
                self.columns.errors.append(msg)
                return False
            if layout_type == 'PLATE_384' and (self.rows.data != 16 or self.columns.data != 24):
                msg = "384-well plate must be 16 rows by 24 columns."
                self.rows.errors.append(msg)
                self.columns.errors.append(msg)
                return False
        elif layout_type == 'CUSTOM_TUBES':
            if not self.num_tubes.data or self.num_tubes.data <= 0:
                self.num_tubes.errors.append("Number of Tubes/Wells is required for Custom type and must be positive.")
                return False
        else: # Should not happen if choices are respected
            self.layout_type.errors.append("Invalid layout type selected.")
            return False
        return True


class LinkPlateToExperimentForm(FlaskForm):
    plate_layout = QuerySelectField('Select Plate Layout', 
                                   query_factory=lambda: PlateLayout.query.order_by(PlateLayout.name).all(),
                                   get_label='name',
                                   allow_blank=False,
                                   validators=[DataRequired()])
    name_in_experiment = StringField('Name for this plate in experiment (e.g., Input Plate 1)',
                                     validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('Link Layout to Experiment')


class WellDataEntrySubForm(FlaskForm): # Base for a single well's custom properties
    # This will be populated dynamically with fields based on WellPropertyDefinitions
    # e.g., sample_id = StringField('Sample ID')
    #       concentration = FloatField('Concentration')
    pass

class WellDataMatrixForm(FlaskForm): # For grid-based (plate) data entry
    # wells = FieldList(FormField(WellDataEntrySubForm)) # This structure might be complex for a grid
    # Instead, fields will be named like 'well_A1_prop_SampleID' directly in the main form class.
    # This form is primarily a container for the submit button and CSRF token.
    submit = SubmitField('Save All Well Data')

class WellDataListForm(FlaskForm): # For list-based (custom tubes) data entry
    # tubes = FieldList(FormField(WellDataEntrySubForm))
    # Similar to matrix, fields named like 'tube_1_prop_SampleID'.
    submit = SubmitField('Save All Tube Data')


# Helper to generate the dynamic form for well data entry
def generate_well_data_form(experiment_plate_link, data=None, existing_well_data=None):
    """
    Generates a form class for entering data for all wells/tubes in a linked plate.
    - experiment_plate_link: The ExperimentPlateLink object.
    - data: request.form data for POST requests.
    - existing_well_data: Dict of {well_identifier: {prop_name: value}}
    """
    plate_layout = experiment_plate_link.plate_layout
    is_grid_layout = plate_layout.layout_type not in ['CUSTOM_TUBES']
    BaseFormClass = WellDataMatrixForm if is_grid_layout else WellDataListForm
    
    class DynamicWellForm(BaseFormClass):
        pass

    well_identifiers = []
    if is_grid_layout:
        for r_idx in range(plate_layout.rows):
            row_char = chr(ord('A') + r_idx)
            for c_idx in range(plate_layout.columns):
                well_identifiers.append(f"{row_char}{c_idx + 1}")
    else: 
        for i in range(plate_layout.num_tubes):
            well_identifiers.append(f"Tube_{i + 1}")

    for well_id_str in well_identifiers:
        current_well_existing_props = existing_well_data.get(well_id_str, {}) if existing_well_data else {}
        for prop_def in plate_layout.custom_property_definitions:
            field_name = f"well_{well_id_str}_prop_{prop_def.id}" 
            label = f"{prop_def.property_name}" 
            current_prop_value = current_well_existing_props.get(prop_def.property_name)
            validators = [Optional()]
            field = None
            if prop_def.property_type == 'TEXT': field = StringField(label, validators=validators, default=current_prop_value)
            elif prop_def.property_type == 'NUMBER': field = StringField(label, validators=validators, default=current_prop_value)
            elif prop_def.property_type == 'BOOLEAN':
                bool_current_value = str(current_prop_value).lower() == 'true'
                field = BooleanField(label, default=bool_current_value) 
            else: field = StringField(label, validators=validators, default=current_prop_value)
            setattr(DynamicWellForm, field_name, field)
            
    return DynamicWellForm(data) if data else DynamicWellForm()

# Forms for Experiment Scheme (Workflow) Management

class ExperimentSchemeForm(FlaskForm):
    name = StringField('Scheme Name', validators=[DataRequired(), Length(max=150)])
    description = TextAreaField('Description', validators=[Optional()])
    submit = SubmitField('Save Scheme')

def get_experiment_instances(): # Factory for QuerySelectField
    # Could be filtered by current_user if appropriate, or all shared instances
    return ExperimentInstance.query.order_by(ExperimentInstance.title).all()

def get_experiment_formats_for_scheme(): # Factory for QuerySelectField
    return ExperimentFormat.query.order_by(ExperimentFormat.name).all()

class SchemeNodeForm(FlaskForm): # Used for creating/editing nodes, often via AJAX/modal
    label = StringField('Node Label', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])
    color = StringField('Color (hex, e.g., #RRGGBB)', default="#FFFFFF", validators=[Optional(), Length(max=50)])
    
    # Optional links to other entities
    linked_experiment_instance = QuerySelectField(
        'Link to Experiment Instance',
        query_factory=get_experiment_instances,
        get_label='title',
        allow_blank=True,
        blank_text='-- None --',
        validators=[Optional()]
    )
    linked_experiment_format = QuerySelectField(
        'Link to Experiment Format',
        query_factory=get_experiment_formats_for_scheme,
        get_label='name',
        allow_blank=True,
        blank_text='-- None --',
        validators=[Optional()]
    )
    # pos_x, pos_y, width, height are usually set by JS on the client side and sent with data
    submit = SubmitField('Save Node') # May or may not be used if handled by JS
