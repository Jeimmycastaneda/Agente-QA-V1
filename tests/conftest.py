import copy

import pytest


class FakeUpload:
    """Stand-in for a Streamlit UploadedFile: exposes .name and .getvalue()."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


# Canonical TEST_CASES/ALERTS/COVERAGE payload, matching config.SCHEMA and
# the fields export/excel.py and export/pdf.py actually read off each case.
_SAMPLE_RESULT = {
    "TEST_CASES": [
        {
            "ID": "CP-AC-LOGIN-00001",
            "Title": "Inicio de sesion exitoso con credenciales validas",
            "Description": "Validar que un usuario registrado pueda iniciar sesion con correo y contrasena validos.",
            "Expected Result": "El sistema autentica al usuario y muestra el panel de cuenta.",
            "Preconditions": "El usuario tiene una cuenta activa registrada.",
            "Product": "Portal Autos Colectivos",
            "Module": "Login",
            "Related Use Case": "Autenticacion de usuario",
            "Criterion": "Autenticacion valida",
            "Scenario": "Login exitoso",
            "Scenario Type": "Positivo",
            "Effort": "Bajo",
            "Coverage": "Completa",
            "Validation Method": "UI",
            "Steps": [
                {
                    "Step #": 1,
                    "Action": "Ingresar correo y contrasena validos.",
                    "Expected value": "Los campos aceptan el texto ingresado.",
                },
                {
                    "Step #": 2,
                    "Action": "Presionar el boton Iniciar sesion.",
                    "Expected value": "El sistema redirige al panel de cuenta.",
                },
            ],
            "Alerts": [],
        },
        {
            "ID": "CP-AC-LOGIN-00002",
            "Title": "Bloqueo de cuenta tras intentos fallidos",
            "Description": "Validar que la cuenta se bloquee tras 5 intentos fallidos de inicio de sesion.",
            "Expected Result": "El sistema bloquea la cuenta y muestra un mensaje de error generico.",
            "Preconditions": "El usuario tiene una cuenta activa registrada.",
            "Product": "Portal Autos Colectivos",
            "Module": "Login",
            "Related Use Case": "Autenticacion de usuario",
            "Criterion": "Bloqueo por intentos fallidos",
            "Scenario": "Bloqueo tras 5 intentos",
            "Scenario Type": "Negativo",
            "Effort": "Medio",
            "Coverage": "Parcial",
            "Validation Method": "BD",
            "Steps": [
                {
                    "Step #": 1,
                    "Action": "Ingresar contrasena incorrecta 5 veces consecutivas.",
                    "Expected value": "El sistema rechaza cada intento con un mensaje de error generico.",
                },
            ],
            "Alerts": [
                {
                    "Alert": "Tiempo de bloqueo no especificado",
                    "Reason": "La fuente no indica cuanto dura el bloqueo de la cuenta.",
                    "Validation Required": "Confirmar con el equipo funcional.",
                },
            ],
        },
    ],
    "ALERTS": [
        {
            "Alert": "Politica de contrasenas no documentada",
            "Reason": "La fuente no especifica requisitos minimos de la contrasena.",
            "Validation Required": "Confirmar con el equipo funcional antes de certificar.",
        },
    ],
    "COVERAGE": [
        {
            "Requirement / Use Case": "Autenticacion de usuario",
            "Criterion": "Autenticacion valida",
            "Scenario": "Login exitoso",
            "Test Case": "CP-AC-LOGIN-00001",
            "Validation Method": "UI",
            "Coverage": "Completa",
            "Alerts": "",
        },
        {
            "Requirement / Use Case": "Autenticacion de usuario",
            "Criterion": "Bloqueo por intentos fallidos",
            "Scenario": "Bloqueo tras 5 intentos",
            "Test Case": "CP-AC-LOGIN-00002",
            "Validation Method": "BD",
            "Coverage": "Parcial",
            "Alerts": "",
        },
    ],
}


@pytest.fixture
def sample_result():
    # Deep copy: tests may mutate the payload freely without cross-test leakage.
    return copy.deepcopy(_SAMPLE_RESULT)
