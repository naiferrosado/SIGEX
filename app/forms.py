from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email

class LoginForm(FlaskForm):
    email = StringField('Correo Institucional', validators=[
        DataRequired(message="El correo es obligatorio."), 
        Email(message="Ingrese un formato de correo válido.")
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message="La contraseña es obligatoria.")
    ])
    recordarme = BooleanField('Recordarme')
    submit = SubmitField('Iniciar')