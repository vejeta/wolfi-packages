#!/usr/bin/env python3
"""
Add keyring configuration to all package YAML files using proper YAML parsing.
"""

import os
import sys
import yaml
from pathlib import Path

def add_keyring_to_yaml(filepath):
    """Add keyring configuration to a package YAML file using YAML parsing."""

    # Read the YAML file
    with open(filepath, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"  ✗ {os.path.basename(filepath)}: YAML parse error: {e}")
            return False

    # Check if already has keyring
    if 'environment' in data and 'contents' in data['environment']:
        if 'keyring' in data['environment']['contents']:
            print(f"  ✓ {os.path.basename(filepath)} already has keyring configuration")
            return False

    # Add keyring and repositories to environment.contents
    if 'environment' not in data:
        data['environment'] = {}

    if 'contents' not in data['environment']:
        data['environment']['contents'] = {}

    # Add keyring before packages
    if 'keyring' not in data['environment']['contents']:
        data['environment']['contents']['keyring'] = [
            'https://packages.wolfi.dev/os/wolfi-signing.rsa.pub'
        ]

    if 'repositories' not in data['environment']['contents']:
        data['environment']['contents']['repositories'] = [
            'https://packages.wolfi.dev/os'
        ]

    # Write back to file, preserving as much formatting as possible
    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"  ✓ Updated {os.path.basename(filepath)}")
    return True

def main():
    packages_dir = 'packages'

    if not os.path.isdir(packages_dir):
        print(f"Error: {packages_dir} directory not found")
        sys.exit(1)

    yaml_files = sorted([f for f in os.listdir(packages_dir) if f.endswith('.yaml')])

    print(f"=== Adding keyring configuration to {len(yaml_files)} package YAML files ===\n")

    updated_count = 0
    for yaml_file in yaml_files:
        filepath = os.path.join(packages_dir, yaml_file)
        if add_keyring_to_yaml(filepath):
            updated_count += 1

    print(f"\n=== Summary: Updated {updated_count} out of {len(yaml_files)} files ===")

    # Verify all files are valid YAML
    print("\n=== Verifying all YAML files are valid ===")
    invalid_files = []
    for yaml_file in yaml_files:
        filepath = os.path.join(packages_dir, yaml_file)
        try:
            with open(filepath, 'r') as f:
                yaml.safe_load(f)
            print(f"  ✓ {yaml_file} is valid")
        except yaml.YAMLError as e:
            print(f"  ✗ {yaml_file} is INVALID: {e}")
            invalid_files.append(yaml_file)

    if invalid_files:
        print(f"\n❌ ERROR: {len(invalid_files)} files have YAML errors:")
        for f in invalid_files:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"\n✓ All {len(yaml_files)} YAML files are valid!")

if __name__ == '__main__':
    main()
