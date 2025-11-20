"""Model utilities for data conversion and field inspection.

Provides utilities for converting Pydantic models and Python objects to various
formats including CSV, YAML, and Markdown representations.
"""

import csv
import io
from typing import Any, Dict, List

import jsonpickle
import yaml
from pydantic import BaseModel


def Is_Non_Complex_Field_Check_By_Value(value: Any) -> bool:
    """Check if a field is a non-complex field using its value.

    Args:
        value: The value to check.

    Returns:
        True if the value is a simple type (str, int, float, bool, None).
    """
    return isinstance(value, (str, int, float, bool, type(None)))


def Is_Non_Complex_Field_Check_By_Type(field_type: Any, root_model_name: str = "RootModel") -> bool:
    """Check if a field is a non-complex field using its type.

    Note: This is not a foolproof method and is based on the assumption that
    complex types have 'RootModel' in their name.

    Args:
        field_type: The field type to check.
        root_model_name: The name to check for in the type string.

    Returns:
        True if the field type does not contain the root_model_name.
    """
    if root_model_name in str(field_type):
        return False
    else:
        return True


class FieldData(BaseModel):
    """Data class representing field metadata.

    Attributes:
        FieldName: The name of the field.
        FieldType: The type of the field as a string.
    """

    FieldName: str
    FieldType: str


def Get_Model_Properties(model: Any) -> List[FieldData]:
    """Extract field properties from a Pydantic model.

    Args:
        model: A Pydantic model class.

    Returns:
        A list of FieldData objects representing the model's fields.
    """
    properties: List[FieldData] = list()
    for field_name, field in model.model_fields.items():
        f: FieldData = FieldData(FieldName=field_name, FieldType=str(field.annotation))
        properties.append(f)
    return properties


def Dict_To_Csv(obj: Dict[str, Any], row_header_columns: List[str], name: str) -> str:
    """Convert a dictionary to CSV format with markdown code fences.

    Args:
        obj: Dictionary where values are row data.
        row_header_columns: List of column headers to include.
        name: Name identifier (currently unused).

    Returns:
        A string containing CSV data wrapped in markdown code fences.
    """
    output: str = "``` csv\n"
    csv_output: io.StringIO = io.StringIO()
    writer = csv.writer(csv_output)
    writer.writerow(row_header_columns)
    for row in obj.values():
        writer.writerow([row[key] for key in row_header_columns])
    output += csv_output.getvalue() + "\n```"
    return output


def List_To_Csv(obj: List[Any], row_header_columns: List[str], name: str) -> str:
    """Convert a list to CSV format with markdown code fences.

    Args:
        obj: List of objects (dicts or objects with __dict__).
        row_header_columns: List of column headers to include.
        name: Name identifier (currently unused).

    Returns:
        A string containing CSV data wrapped in markdown code fences.
    """
    output: str = "``` csv\n"
    csv_output: io.StringIO = io.StringIO()
    writer = csv.writer(csv_output)
    writer.writerow(row_header_columns)
    for row in obj:
        if not isinstance(row, dict):
            try:
                row = row.__dict__
            except Exception:
                print(f"Could not convert {row} to dictionary")
        writer.writerow([row[key] for key in row_header_columns])
    output += csv_output.getvalue() + "\n```"
    return output


def Listable_Object_To_Csv(obj: List[Any], row_type: Any) -> str:
    """Convert a list of typed objects to CSV format with automatic header inference.

    Args:
        obj: List of objects to convert.
        row_type: The type/model of the objects in the list.

    Returns:
        A string containing CSV data wrapped in markdown code fences.
    """
    output: str = "``` csv\n"
    csv_output: io.StringIO = io.StringIO()
    writer = csv.writer(csv_output)
    headers: List[str] = [
        prop.FieldName
        for prop in Get_Model_Properties(row_type)
        if Is_Non_Complex_Field_Check_By_Type(prop.FieldType)
    ]
    writer.writerow(headers)
    for row in obj:
        writer.writerow([getattr(row, header, None) for header in headers])
    output += csv_output.getvalue() + "\n```"
    return output


def Object_To_Yaml(obj: Any, strip_complex_fields: bool = False) -> str:
    """Convert an object to YAML format with markdown code fences.

    Args:
        obj: Object to convert (must have __dict__ attribute).
        strip_complex_fields: If True, only include non-complex fields.

    Returns:
        A string containing YAML data wrapped in markdown code fences.
    """
    obj_dict: Dict[str, Any] = obj.__dict__
    output: str = "``` yaml\n"
    if strip_complex_fields:
        obj_dict = {k: v for k, v in obj.__dict__.items() if Is_Non_Complex_Field_Check_By_Value(v)}
    yaml_output: str = yaml.dump(obj_dict, default_flow_style=False)
    return output + yaml_output + "\n```"


def Object_To_Markdown(obj: Any, name: str) -> str:
    """Convert an object to Markdown format using JSON serialization.

    Args:
        obj: Object to convert.
        name: Name identifier (currently unused).

    Returns:
        A JSON string representation of the object.
    """
    val: str = jsonpickle.dumps(obj)
    return val
