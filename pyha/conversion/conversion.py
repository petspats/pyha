import inspect
from pathlib import Path
from typing import List

from redbaron import RedBaron

from pyha.conversion.converter import convert
from pyha.conversion.extract_datamodel import DataModel
from pyha.conversion.top_generator import TopGenerator


class MultipleNodesError(Exception):
    pass


class Conversion:
    """
    input: stimulated object
    outputs:
        *comonent vhdl files
        *top file
        *top input types
        *top output types
    """

    def __init__(self, main_obj):
        self.main_obj = main_obj
        main_red = self.get_objects_rednode(main_obj)
        main_datamodel = DataModel(main_obj)
        # main_datamodel = None
        self.main_conversion = convert(main_red, caller=None, datamodel=main_datamodel)

        self.top_vhdl = TopGenerator(main_obj)

    @property
    def inputs(self) -> List[object]:
        return self.top_vhdl.get_object_inputs()

    @property
    def outputs(self) -> List[object]:
        return self.top_vhdl.get_object_return()

    def write_vhdl_files(self, base_dir: Path) -> List[Path]:
        paths = [base_dir / 'main.vhd']
        with paths[-1].open('w') as f:
            f.write(str(self.main_conversion))

        paths.append(base_dir / 'top.vhd')
        with paths[-1].open('w') as f:
            f.write(self.top_vhdl.make())

        return paths

    def discover_child_entities(self):
        # TODO: future
        pass

    def get_objects_rednode(self, obj):
        source_path = self.get_objects_source_path(obj)
        source = open(source_path).read()
        red_list = RedBaron(source)('class', name=obj.__class__.__name__)
        if len(red_list) != 1:
            raise MultipleNodesError('Found {} definitions of "{}" class'.
                                     format(len(red_list), obj.__class__.__name__))

        return red_list[0]

    def get_objects_source_path(self, obj) -> str:
        return inspect.getsourcefile(type(obj))
