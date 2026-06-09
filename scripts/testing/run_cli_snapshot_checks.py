#!/usr/bin/env python3
import sys
import argparse
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

def load_parser_from_file(path: Path) -> argparse.ArgumentParser:
    if not path.exists():
        print(f"Error: Path {path} does not exist", file=sys.stderr)
        sys.exit(1)
    
    # Add parent dir to sys.path so nested imports work
    parent_str = str(path.parent)
    if parent_str not in sys.path:
        sys.path.insert(0, parent_str)

    try:
        loader = SourceFileLoader("server_module", str(path))
        spec = importlib.util.spec_from_file_location("server_module", str(path), loader=loader)
        if spec is None or spec.loader is None:
            print(f"Error: Could not load spec for {path}", file=sys.stderr)
            sys.exit(1)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Error: Exception executing module {path}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    if not hasattr(module, "build_parser"):
        print(f"Error: Module {path} does not define build_parser", file=sys.stderr)
        sys.exit(1)
    
    return module.build_parser()

def serialize_action(action: argparse.Action) -> dict:
    # Format type representation safely
    type_str = "None"
    if action.type is not None:
        type_str = action.type.__name__ if hasattr(action.type, "__name__") else str(action.type)

    return {
        "option_strings": action.option_strings,
        "dest": action.dest,
        "nargs": action.nargs,
        "const": action.const,
        "default": action.default,
        "type": type_str,
        "choices": list(action.choices) if action.choices is not None else None,
        "required": action.required,
        "action_type": type(action).__name__,
    }

def serialize_parser(parser: argparse.ArgumentParser) -> dict:
    data = {
        "description": parser.description,
        "actions": {},
        "subcommands": {}
    }
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for cmd_name, sub_parser in action.choices.items():
                data["subcommands"][cmd_name] = serialize_parser(sub_parser)
        elif isinstance(action, argparse._HelpAction):
            # Skip help action to avoid noise if help text formats vary slightly,
            # but we can include it if we want strict help equivalence.
            continue
        else:
            key = action.option_strings[0] if action.option_strings else f"positional:{action.dest}"
            data["actions"][key] = serialize_action(action)
    return data

def compare_structures(orig: dict, new: dict, path_prefix: str = "") -> list:
    diffs = []
    
    # Compare description
    if orig["description"] != new["description"]:
        diffs.append(f"{path_prefix}Description mismatch: original='{orig['description']}', new='{new['description']}'")
    
    # Compare actions keys
    orig_actions = set(orig["actions"].keys())
    new_actions = set(new["actions"].keys())
    
    for missing in orig_actions - new_actions:
        diffs.append(f"{path_prefix}Missing action option: {missing}")
    for extra in new_actions - orig_actions:
        diffs.append(f"{path_prefix}Extra action option: {extra}")
        
    for common in orig_actions & new_actions:
        o_act = orig["actions"][common]
        n_act = new["actions"][common]
        for field in ["option_strings", "dest", "nargs", "const", "default", "type", "choices", "required", "action_type"]:
            if o_act[field] != n_act[field]:
                diffs.append(f"{path_prefix}Action {common} field '{field}' mismatch: original={o_act[field]}, new={n_act[field]}")
                
    # Compare subcommands keys
    orig_sub = set(orig["subcommands"].keys())
    new_sub = set(new["subcommands"].keys())
    
    for missing in orig_sub - new_sub:
        diffs.append(f"{path_prefix}Missing subcommand: {missing}")
    for extra in new_sub - orig_sub:
        diffs.append(f"{path_prefix}Extra subcommand: {extra}")
        
    for common in orig_sub & new_sub:
        diffs.extend(compare_structures(orig["subcommands"][common], new["subcommands"][common], f"{path_prefix}{common} -> "))
        
    return diffs

def main():
    workspace_root = Path(__file__).resolve().parent.parent.parent
    original_path = workspace_root / "templates" / "server.py.bak"
    new_path = workspace_root / "templates" / "server.py"
    
    print(f"Comparing parser structures:")
    print(f"  Original: {original_path}")
    print(f"  New:      {new_path}")
    
    # Load original parser
    original_parser = load_parser_from_file(original_path)
    # Load new parser
    new_parser = load_parser_from_file(new_path)
    
    orig_struct = serialize_parser(original_parser)
    new_struct = serialize_parser(new_parser)
    
    diffs = compare_structures(orig_struct, new_struct)
    
    if diffs:
        print("\nFAIL: CLI parser structures do not match!")
        for diff in diffs:
            print(f"  - {diff}")
        sys.exit(1)
    else:
        print("\nSUCCESS: CLI parser structures match 100%!")
        sys.exit(0)

if __name__ == "__main__":
    main()
