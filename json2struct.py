from pathlib import Path
import os
import sys, getopt
import json
import re
import copy
from typing import List
import codecs

StrList = List[str]
DictList = List[dict]


def get_unique_structs(struct_info: dict) -> DictList:
    """
    Returns a list containing the type mapping of all unique
    structs (object types) in a struct datatype mapping.
    """
    unique_structs = []

    if isinstance(struct_info, dict):
        unique_structs.append(struct_info)

    for k, v in struct_info.items():
        if isinstance(v, dict):
            unique_structs += get_unique_structs(v)

    return unique_structs


def generate_field_name(field_name: str) -> str:
    """
    Turns a snake_case field name into a PascalCase field name.
    """
    split_snake = field_name.split("_")
    if len(split_snake) == 1:
        struct_name = f"{field_name[0].upper()}{field_name[1:]}"
    else:
        split_snake = [s.capitalize() for s in split_snake]

        struct_name = "".join(split_snake)

    return struct_name


def retype_nested_types(struct_info: dict) -> dict:
    """
    Recursively finds any nested object types in `struct_info` and
    replaces the mapping info with the nested `__struct_name` field.
    """
    retyped_struct = copy.deepcopy(struct_info)

    for k, v in struct_info.items():
        if isinstance(v, dict):
            if v["__is_type_array"]:
                retyped_struct[k] = f"[]{v['__struct_name']}"
            else:
                retyped_struct[k] = v["__struct_name"]

    return retyped_struct


def create_struct_strings(struct_info: dict, omit_empty=True) -> StrList:
    """
    Turns struct info maps into multiline strings which can get
    written to a .go file.

    Eyyyy.
    """
    unique_structs = get_unique_structs(struct_info)

    struct_strings = []

    for i in range(len(unique_structs)):
        unique_structs[i] = retype_nested_types(unique_structs[i])

    for u in unique_structs:
        struct_name = u.pop("__struct_name")
        u.pop("__is_type_array")
        struct_string = f"type {struct_name} struct " + "{\n"
        for k, v in u.items():
            field_name = generate_field_name(k)
            if omit_empty:
                struct_tag = f"`json:\"{k},omitempty\"`"
            else:
                struct_tag = f"`json:\"{k}\"`"
            struct_string += f"\t{field_name}\t{v}\t{struct_tag}\n"
        struct_string += "}"

        struct_strings.append(struct_string)

    return struct_strings


def write_struct_file(struct_strings: StrList, package_name: str, output_filename: str):
    with open(f"{output_filename}", "w") as structfile:
        structfile.write(f"package {package_name}\n\n")
        for s in struct_strings:
            structfile.write(s + "\n\n")


go_types_map = {
    "str": "string",
    "bool": "bool",
    "int": "int",
    "float": "float32",
    # "list":"[]float32",
}

typename_re = re.compile("\<class\s\'(.+)\'\>")


def get_items_by_type(json_data, datatype):
    items = []

    for k, v in json_data.items():
        if isinstance(v, datatype):
            items.append(k)

    return items


def get_type_name(type_):
    return typename_re.search(str(type_)).groups(0)[0]


def check_array_type(array):
    """
    Checks an array to ensure that all entries are of the same type.
    Otherwise, shit'll get funky with struct building.
    """
    zero_index_type = type(array[0])
    is_uniform_type = True

    for a in array:
        if not isinstance(a, zero_index_type):
            is_uniform_type = False

    zero_index_type = get_type_name(zero_index_type)

    return (is_uniform_type, zero_index_type)


def assure_uniform_object_structure(obj_array):
    """
    Checks if all dicts in a list of dicts have the same structure (keys and types)
    """
    all_same_keys = True
    all_same_value_types = True

    base_keys = list(obj_array[0].keys())
    base_val_types = {k: type(v) for k, v in obj_array[0].items()}

    if len(obj_array) == 1:
        pass
    else:
        for obj in obj_array[1:]:
            keys = list(obj.keys())
            val_types = {k: type(v) for k, v in obj.items()}
            all_same_keys = keys == base_keys
            all_same_value_types = all([val_types[k] == base_val_types[k] for k in keys])

    return (all_same_keys, all_same_value_types)


def make_key_type_map(json_data):
    key_type_map = {
        k: type(v) for k, v in json_data.items()
    }

    return key_type_map


def generate_struct_info(json_data, struct_name, is_array=False):
    """
    Not sure how I wrote this sober
    """
    struct_info = {
        "__struct_name": struct_name,
        "__is_type_array": is_array
    }

    key_type_map = make_key_type_map(json_data)

    for k, v in key_type_map.items():
        val_type_str = get_type_name(v)

        json_item = json_data[k]

        if val_type_str in go_types_map:
            struct_info[k] = go_types_map[val_type_str]
        elif val_type_str == "dict":
            struct_info[k] = generate_struct_info(json_item, generate_field_name(k))
        elif val_type_str == "list":
            array_type_info = check_array_type(json_item)

            if array_type_info[0]:
                if array_type_info[1] == "dict":
                    if all(assure_uniform_object_structure(json_item)):
                        array_struct_name = f"{generate_field_name(k)}List"
                        struct_info[k] = generate_struct_info(json_item[0], array_struct_name, is_array=True)
                    else:
                        struct_info[k] = "[]interface{}"
                else:
                    zero_index_type = get_type_name(type(json_item[0]))
                    if zero_index_type == 'list':
                        zero_index_type = get_type_name(type(json_item[0][0]))
                        # print(zero_index_type,"zero_index_type")
                        zero_index_type = go_types_map[zero_index_type]
                        struct_info[k] = f"[][]{zero_index_type}"
                    else:
                        zero_index_type = go_types_map[zero_index_type]
                        struct_info[k] = f"[]{zero_index_type}"
            else:
                struct_info[k] = "[]interface{}"

    return struct_info


package_name = "json"


def write(store_dir):
    p = f'{store_dir}/{package_name}.go'
    with codecs.open(p, "w", "utf-8") as f:
        f.write(f"package {package_name}\n\n")


def parseJson(root_dir='./json', store_dir='"./go"'):
    path = Path(root_dir)
    write(store_dir)
    p = f'{store_dir}/{package_name}.go'
    with codecs.open(p, "a", "utf-8") as f:
        all_json_file = list(path.glob('**/*.json'))
        for json_file in all_json_file:
            with open(json_file, "r") as json_file:
                json_data = json.load(json_file)
            if isinstance(json_data, list):
                json_data = json_data[0]
            name = os.path.splitext(os.path.basename(json_file.name))[0]
            struct_info = generate_struct_info(json_data, name, True)
            struct_strings = create_struct_strings(struct_info, False)
            for s in struct_strings:
                f.write(s + "\n\n")


def main(argv):
    inputfile = ''
    outputfile = ''
    try:
        opts, args = getopt.getopt(argv, "hi:o:", ["ifile=", "ofile="])
    except getopt.GetoptError:
        print('json2struct.py -i <inputfile> -o <outputfile>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('json2struct.py -i <inputfile> -o <outputfile>')
            sys.exit()
        elif opt in ("-i", "--ifile"):
            inputfile = arg
        elif opt in ("-o", "--ofile"):
            outputfile = arg

    print('输入的文件为:', inputfile)
    print('输出的文件为:', outputfile)
    parseJson(inputfile, outputfile)
    print('恭喜生成完成!!')


if __name__ == '__main__':
    main(sys.argv[1:])
