# json_manager.py

import json

def load_json(file_path):
    """Load JSON data from a file. Create file if it does not exist."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(file_path, data):
    """Save JSON data to a file with UTF-8 encoding."""
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def update_json(file_path, category, emails, company_name):
    """Update the JSON file with new emails and company names under the specified category."""
    data = load_json(file_path)
    
    if category not in data:
        data[category] = []

    for email in emails:
        data[category].append({"email": email, "name": company_name})
    
    save_json(file_path, data)


