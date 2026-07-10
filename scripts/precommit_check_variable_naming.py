import re
import sys
import os

SNAKE_CASE_REGEX: re.Pattern = re.compile(r"^[a-z_][a-z0-9_]*$")
BAD_NAMES: set[str] = {"x", "temp", "data", "value"}
EXCLUDED_FILES: list[str] = [
    "models.py",
    "generic_models.py",
    "apps.py",
    "serializers.py",
    "views.py",
    "filters.py",
    "priority_queue.py",
]
EXCLUDED_FOLDERS: list[str] = ["migrations"]

# Regex to detect function/method definitions
FUNCTION_DEF_REGEX: re.Pattern = re.compile(
    r"^\s*(def|class)\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\("
)


def should_skip_file(file_path: str) -> bool:
    """Check if the file should be skipped (models.py or any migration file)."""
    filename = os.path.basename(file_path)
    return filename in EXCLUDED_FILES or any(
        folder in file_path for folder in EXCLUDED_FOLDERS
    )


def is_function_call(line: str) -> bool:
    """Check if the line contains a function call."""
    return "(" in line and ")" in line and "=" not in line.split("(")[0]


def skip_parentheses_content(lines: list[str]) -> list[str]:
    """Remove all content inside parentheses (including multi-line content)."""
    result = []
    paren_level = 0

    for line in lines:
        line = line.strip()
        if "(" in line:
            paren_level += line.count("(")
        if ")" in line:
            paren_level -= line.count(")")

        # If inside parentheses, skip this line
        if paren_level > 0:
            continue

        # Otherwise, add this line to result
        result.append(line)

    return result


def check_variable_naming(file_path: str) -> list[str]:
    """Checks if variables in a file follow snake_case, avoid bad names, and have type hints."""
    if should_skip_file(file_path):
        return []

    errors: list[str] = []
    inside_function: bool = False
    typed_vars: set[str] = set()
    missing_type_hint_reported: set[str] = set()

    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        lines = skip_parentheses_content(lines)

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Detect function/method/class definitions
            if FUNCTION_DEF_REGEX.match(line):
                inside_function = True
                continue

            # Exit function/class scope if we encounter an empty line or return to global scope
            if inside_function and (not line or not line.startswith((" ", "\t"))):
                inside_function = False

            # Skip function calls completely
            if is_function_call(line):
                continue

            # Skip lines with function calls on the right side of assignment
            if "=" in line and ("(" in line.split("=")[1] or ")" in line.split("=")[1]):
                continue

            # Check for variable assignments
            if "=" in line and not line.lstrip().startswith(("def ", "class ")):
                # Split on = and get the left part
                var_part = line.split("=")[0].strip()

                # Handle type hints by splitting on :
                var_name = var_part.split(":")[0].strip()
                has_type_hint: bool = ":" in var_part
                if has_type_hint:
                    typed_vars.add(var_name)

                # Ignore all-uppercase variables (constants like BASE_DIR, SECRET_KEY, etc.)
                if var_name.isupper():
                    continue

                if var_name.isidentifier():  # Ensure it's a valid Python identifier
                    if not SNAKE_CASE_REGEX.match(var_name):
                        errors.append(
                            f"{file_path}:{line_number} - Variable '{var_name}' should be in snake_case."
                        )
                    if var_name in BAD_NAMES:
                        errors.append(
                            f"{file_path}:{line_number} - Variable '{var_name}' is too generic; use a meaningful name."
                        )

                    # Check for missing type hints
                    # Only require a type hint at the first assignment site.
                    # Re-assignments to an already-typed variable should not be forced
                    # to repeat the annotation (e.g. `flag: bool = False; flag = True`).
                    if (not has_type_hint) and (var_name not in typed_vars):
                        if var_name in missing_type_hint_reported:
                            continue
                        missing_type_hint_reported.add(var_name)
                        errors.append(
                            f"{file_path}:{line_number} - Variable '{var_name}' is missing a type hint."
                        )

    return errors


def main() -> None:
    """Main function to check all Python files passed as arguments."""
    filenames: list[str] = sys.argv[1:]
    all_errors: list[str] = []

    for file in filenames:
        if file.endswith(".py"):  # Only check Python files
            all_errors.extend(check_variable_naming(file))

    if all_errors:
        for error in all_errors:
            print(error)
        sys.exit(1)  # Exit with error status
    sys.exit(0)


if __name__ == "__main__":
    main()
