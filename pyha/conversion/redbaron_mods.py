import logging
import textwrap
from contextlib import suppress

import pyha
from parse import parse
from pyha.common.core import SKIP_FUNCTIONS
from pyha.common.fixed_point import Sfix
from pyha.common.util import get_iterable, tabber, formatter
from pyha.conversion.python_types_vhdl import escape_reserved_vhdl, VHDLModule, init_vhdl_type, VHDLEnum, VHDLList
from redbaron import Node, EndlNode, DefNode, AssignmentNode, TupleNode, CommentNode, AssertNode, FloatNode, \
    IntNode, UnitaryOperatorNode, GetitemNode, inspect, CallNode
from redbaron.base_nodes import DotProxyList
from redbaron.nodes import AtomtrailersNode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def file_header():
    template = '-- generated by pyha {}'
    return template.format(pyha.__version__)


class NodeVHDL:
    def __init__(self, red_node, parent=None):
        self.red_node = red_node
        self.parent = parent
        self.target = None
        self.value = None
        self.first = None
        self.second = None
        self.test = None
        self.arguments = None
        self.name = None
        self.iterator = None

        for x in red_node._dict_keys:
            self.__dict__[x] = redbaron_node_to_vhdl_node(red_node.__dict__[x], caller=self)

        for x in red_node._list_keys:
            if 'format' not in x:
                self.__dict__[x] = []
                for xj in red_node.__dict__[x]:
                    # function is NOT simulated, dont convert it
                    if isinstance(xj, DefNode) and getattr(convert_obj, xj.name).calls == 0:
                        logger.warning(f'Class "{red_node.name}" function "{xj.name}" was NOT called during simulation, not converting it!')
                        continue
                    self.__dict__[x].append(redbaron_node_to_vhdl_node(xj, caller=self))

        for x in red_node._str_keys:
            self.__dict__[x] = red_node.__dict__[x]

    def __str__(self):
        return str(self.red_node)


class NameNodeVHDL(NodeVHDL):
    def __str__(self):
        return escape_reserved_vhdl(self.red_node.value)


class AtomtrailersNodeVHDL(NodeVHDL):
    def is_function_call(self):
        return any(isinstance(x, CallNodeVHDL) for x in self.value)

    def __str__(self):
        ret = ''
        for i, x in enumerate(self.value):
            # add '.' infront if NameNode
            new = '.{}' if isinstance(x, NameNodeVHDL) and i != 0 else '{}'

            if x.value == 'len' and isinstance(x.red_node.next, CallNode):
                continue

            if isinstance(x.red_node, CallNode) and x.red_node.previous.value == 'len':
                new = f"{str(x)[1:-1]}'length"

            ret += new.format(x)

        return ret


class TupleNodeVHDL(NodeVHDL):
    def __iter__(self):
        return iter(self.value)

    def __str__(self):
        return ','.join(str(x) for x in self.value)


class AssignmentNodeVHDL(NodeVHDL):
    def __str__(self):
        r = ''
        if isinstance(self.red_node.target, TupleNode) or isinstance(self.red_node.value, TupleNode):
            # multiple assignment: a,b = 1, 2
            for target, value in zip(self.target, self.value):
                r += f'{target} := {value};\n'

        elif self.red_node.operator != '':
            raise Exception('{} -> cannot convert +=, -=, /=, *= :(')
        else:
            r = f'{self.target} := {self.value};'
        return r


class ReturnNodeVHDL(NodeVHDL):
    def __str__(self):
        ret = []
        for i, value in enumerate(get_iterable(self.value)):
            line = f'ret_{i} := {value}'
            if line[-1] != ';':
                line += ';'
            ret.append(line)

        ret += ['return;']
        return '\n'.join(ret)


class ComparisonNodeVHDL(NodeVHDL):
    def __str__(self):
        return f'{self.first} {self.value} {self.second}'


class BinaryOperatorNodeVHDL(ComparisonNodeVHDL):
    def __str__(self):

        # test if we are dealing with array appending ([a] + b)
        if self.value == '+':
            if isinstance(self.first, ListNodeVHDL) or isinstance(self.second, ListNodeVHDL):
                return f'{self.first} & {self.second}'
        elif self.value == '//':
            return f'integer({self.first} / {self.second})'
        elif self.value == '>>':
            self.value = 'sra'
        elif self.value == '<<':
            self.value = 'sla'
        elif self.value == '&':
            self.value = 'and'
        elif self.value == '|':
            self.value = 'or'
        elif self.value == '^':
            self.value = 'xor'

        return f'{self.first} {self.value} {self.second}'


class BooleanOperatorNodeVHDL(ComparisonNodeVHDL):
    pass


class AssociativeParenthesisNodeVHDL(NodeVHDL):
    def __str__(self):
        return f'({self.value})'


class ComparisonOperatorNodeVHDL(NodeVHDL):
    def __str__(self):
        if self.first == '==':
            return '='
        elif self.first == '!=':
            return '/='
        else:
            return super().__str__()


class IfelseblockNodeVHDL(NodeVHDL):
    def __str__(self):
        body = '\n'.join(str(x) for x in self.value)
        return body + '\nend if;'


class IfNodeVHDL(NodeVHDL):
    def __str__(self):
        body = '\n'.join(tabber(str(x)) for x in self.value)
        return f'if {self.test} then\n{body}'


class ElseNodeVHDL(NodeVHDL):
    def __str__(self):
        body = '\n'.join(tabber(str(x)) for x in self.value)
        return f'else\n{body}'


class ElifNodeVHDL(NodeVHDL):
    def __str__(self):
        body = '\n'.join(tabber(str(x)) for x in self.value)
        return f'elsif {self.test} then\n{body}'


class DefNodeVHDL(NodeVHDL):
    def __init__(self, red_node, parent=None):
        super().__init__(red_node, parent)

        # todo: remove me after refactorings
        try:
            self.data = getattr(convert_obj, self.name)
        except AttributeError:
            self.data = None

        self.name = escape_reserved_vhdl(self.name)

        # collect multiline comment
        self.multiline_comment = ''
        if isinstance(self.value[0], StringNodeVHDL):
            self.multiline_comment = str(self.value[0])
            del self.value[0]

        # remove last line,if it is \n
        if isinstance(self.value[-1], EndlNodeVHDL):
            del self.value[-1]

        self.arguments = self.build_arguments()
        self.variables = self.build_variables()

    def build_arguments(self):
        # function arguments
        argnames = inspect.getfullargspec(self.data.func).args[1:]  # skip the first 'self'
        argvals = list(self.data.last_args)
        args = [init_vhdl_type(name, val, val) for name, val in zip(argnames, argvals)]
        args = ['self:inout self_t'] + [f'{x._pyha_name()}: {x._pyha_type()}' for x in args]

        # function returns -> need to add as 'out' arguments in VHDL
        rets = []
        if self.data.last_return is not None:
            if isinstance(self.data.last_return, tuple):  # multiple returns
                rets = [init_vhdl_type(f'ret_{i}', val, val)
                        for i, val in enumerate(get_iterable(self.data.last_return))]
            else:
                rets = [init_vhdl_type(f'ret_{0}', self.data.last_return, self.data.last_return)]
            rets = [f'{x._pyha_name()}:out {x._pyha_type()}' for x in rets]

        return '; '.join(args + rets)

    def build_variables(self):
        argnames = inspect.getfullargspec(self.data.func).args
        variables = [init_vhdl_type(name, val, val)
                     for name, val in self.data.locals.items()
                     if name not in argnames]

        variables = [f'variable {x._pyha_name()}: {x._pyha_type()};' for x in variables]
        return '\n'.join(variables)

    def build_body(self):
        return '\n'.join(str(x) for x in self.value)

    def build_function(self, prototype_only=False):
        template = textwrap.dedent("""\
            procedure {NAME}{ARGUMENTS} is
            {MULTILINE_COMMENT}
            {VARIABLES}
            begin
            {BODY}
            end procedure;""")

        args = f'({self.arguments})' if len(self.arguments) > 2 else ''
        sockets = {'NAME': self.name,
                   'MULTILINE_COMMENT': self.multiline_comment,
                   'ARGUMENTS': args,
                   'VARIABLES': tabber(self.variables) if self.variables else '',
                   'BODY': tabber(self.build_body())}

        if prototype_only:
            return template.format(**sockets).splitlines()[0][:-3] + ';'
        return template.format(**sockets)

    def __str__(self):
        return self.build_function()


class DefArgumentNodeVHDL(NodeVHDL):
    # this node is not used. arguments are inferred from datamodel!
    pass


class PassNodeVHDL(NodeVHDL):
    def __str__(self):
        return ''


class CallNodeVHDL(NodeVHDL):
    def __str__(self):
        base = '(' + ', '.join(str(x) for x in self.value) + ')'

        # find if this call is part of assignment node?
        p = self.red_node.parent
        is_assign = False
        while p is not None:
            if type(p) == AssignmentNode:
                is_assign = True
                break
            p = p.parent

        if not is_assign and isinstance(self.red_node.next_recursive, EndlNode):
            base += ';'
        return base


class CallArgumentNodeVHDL(NodeVHDL):
    def __str__(self):
        # transform keyword arguments, = to =>
        if self.target is not None:
            return f'{self.target}=>{self.value}'

        return str(self.value)


class IntNodeVHDL(NodeVHDL):
    pass


class FloatNodeVHDL(NodeVHDL):
    pass


class UnitaryOperatorNodeVHDL(NodeVHDL):
    pass


class AssertNodeVHDL(NodeVHDL):
    def __str__(self):
        return '--' + super().__str__()


class PrintNodeVHDL(NodeVHDL):
    def __str__(self):
        if isinstance(self.red_node.value[0], TupleNode):
            raise Exception(f'{self.red_node} -> print only supported with one Sfix argument!')
        return f"report to_string{self.value[0]};"



class ListNodeVHDL(NodeVHDL):
    def __str__(self):
        if len(self.value) == 1:
            return str(self.value[0])  # [a] -> a
        else:
            ret = f'({", ".join(str(x) for x in self.value)})'
            return ret


class EndlNodeVHDL(NodeVHDL):
    def __str__(self):
        if isinstance(self.red_node.previous_rendered, CommentNode):
            return '--' + str(self.red_node.previous_rendered)[1:]
        return ''


class HexaNodeVHDL(NodeVHDL):
    def __str__(self):
        return f'16#{self.value[2:]}#'


class CommentNodeVHDL(NodeVHDL):
    def __str__(self):
        return '--' + self.value[1:]


class StringNodeVHDL(NodeVHDL):
    """ Multiline comments come here """

    def __str__(self):
        if self.value[:3] == '"""' and self.value[-3:] == '"""':
            r = [x.strip() for x in self.value[3:-3].splitlines()]
            r = '\n-- '.join(x for x in r if x != '')
            return '-- ' + r

        return self.value[1:]


# this is mostly array indexing
class GetitemNodeVHDL(NodeVHDL):
    # turn python [] indexing to () indexing

    def get_index_target(self):
        ret = ''
        for x in self.parent.value:
            if x is self:
                break
            ret += '.' + str(x)
        return ret[1:]

    def is_negative_indexing(self, obj):
        return isinstance(obj, UnitaryOperatorNodeVHDL) and int(str(obj)) < 0

    def __str__(self):
        if self.is_negative_indexing(self.value):
            target = self.get_index_target()
            return f"({target}'length{self.value})"

        return f'({self.value})'


class SliceNodeVHDL(GetitemNodeVHDL):
    def get_index_target(self):
        return '.'.join(str(x) for x in self.parent.parent.value[:-1])

    # Example: [0:5] -> (0 to 4)
    # x[0:-1] -> x(0 to x'high-1)
    def __str__(self):
        if self.upper is None:
            upper = f"{self.get_index_target()}'high"
        else:
            # vhdl includes upper limit, subtract one to get same behaviour as in python
            upper = f'({self.upper})-1'

        if self.is_negative_indexing(self.upper):
            target = self.get_index_target()
            upper = f"{target}'high{self.upper}"

        lower = 0 if self.lower is None else self.lower
        return f'{lower} to {upper}'


class ForNodeVHDL(NodeVHDL):
    def __str__(self):
        template = textwrap.dedent("""\
                for {ITERATOR} in {RANGE} loop
                {BODY}
                end loop;""")

        sockets = {'ITERATOR': str(self.iterator)}
        sockets['RANGE'] = self.range_to_vhdl(str(self.target))
        sockets['BODY'] = '\n'.join(tabber(str(x)) for x in self.value)
        return template.format(**sockets)

    def range_to_vhdl(self, pyrange):
        # this for was transforemed by 'redbaron_pyfor_to_vhdl'
        if str(self.iterator) == '\\_i_\\':
            return f"{pyrange}'range"

        range_len_pattern = parse("\\range\\({}'length)", pyrange)
        if range_len_pattern is not None and ',' not in range_len_pattern[0]:
            return range_len_pattern[0] + "'range"
        else:
            range_pattern = parse('\\range\\({})', pyrange)
            if range_pattern is not None:
                two_args = parse('{},{}', range_pattern[0])
                if two_args is not None:
                    # todo: handle many more cases
                    len = parse("{}'length", two_args[1].strip())
                    if len is not None:
                        return f"{two_args[0].strip()} to ({len[0]}'length) - 1"

                    len = parse("{}'length{}", two_args[1].strip())
                    if len is not None:
                        return f"{two_args[0].strip()} to ({len[0]}'length{len[1]}) - 1"

                    return f'{two_args[0].strip()} to ({two_args[1].strip()}) - 1'
                else:
                    len = parse("{}'length{}", range_pattern[0])
                    if len is not None:
                        return f"0 to ({len[0]}'length{len[1]}) - 1"
                    return f'0 to ({range_pattern[0]}) - 1'

        # at this point range was not:
        # range(len(x))
        # range(x)
        # range(x, y)
        # assume
        assert 0


class ClassNodeVHDL(NodeVHDL):
    def __init__(self, red_node, parent=None):
        super().__init__(red_node, parent)

        # todo: remove me after refactorings
        try:
            self.data = VHDLModule('-', convert_obj)
        except AttributeError:
            self.data = None
        # collect multiline comment
        self.multiline_comment = ''
        if len(self.value) and isinstance(self.value[0], StringNodeVHDL):
            self.multiline_comment = str(self.value[0])
            del self.value[0]

    def get_function(self, name):
        f = [x for x in self.value if str(x.name) == name]
        assert len(f)
        return f[0]

    def build_imports(self):
        template = textwrap.dedent("""\
            library ieee;
                use ieee.std_logic_1164.all;
                use ieee.numeric_std.all;
                use ieee.fixed_float_types.all;
                use ieee.fixed_pkg.all;
                use ieee.math_real.all;

            library work;
                use work.PyhaUtil.all;
                use work.Typedefs.all;
                use work.all;
            {IMPORTS}""")

        # add all converted classes to imports
        # look: https://github.com/tgingold/ghdl/issues/209
        from pyha.conversion.conversion import Conversion
        imports = [f'use work.{x}.all;' for x in Conversion.converted_names]
        return template.format(IMPORTS=formatter(imports))

    def build_deepcopy(self, prototype_only=False):
        template = textwrap.dedent("""\
            procedure pyha_deepcopy(self:inout self_t; other: in self_t) is
                -- copy 'other' to 'self.next'. ':=' cannot be used as it would directly copy to 'self'
            begin
            {DATA}
            end procedure;""")

        if prototype_only:
            return template.splitlines()[0][:-3] + ';'
        data = [x.pyha_deepcopy() for x in self.data.elems]
        return template.format(DATA=formatter(data))

    def build_list_deepcopy(self, prototype_only=False):
        template = textwrap.dedent("""\
            procedure pyha_list_deepcopy(self:inout {DTYPE}; other: in {DTYPE}) is
                -- run deepcopy for each list element
            begin
                for i in self'range loop
                    pyha_deepcopy(self(i), other(i));
                end loop;
            end procedure;""")

        dtype = self.data._pyha_arr_type_name()
        template = template.format(DTYPE=dtype)
        if prototype_only:
            return template.splitlines()[0][:-3] + ';'
        return template

    def build_reset(self, prototype_only=False):
        template = textwrap.dedent("""\
            procedure pyha_reset(self:inout self_t) is
                -- executed on reset signal. Reset values are determined from initial values of Python variables.
            begin
            {DATA}
                pyha_update_registers(self);
            end procedure;""")

        if prototype_only:
            return template.splitlines()[0][:-3] + ';'
        data = [x._pyha_reset() for x in self.data.elems]
        return template.format(DATA=formatter(data))

    def build_reset_constants(self, prototype_only=False):
        template = textwrap.dedent("""\
            procedure pyha_reset_constants(self:inout self_t) is
                -- reset CONSTANTS, executed before 'main'. Helps synthesis tools to determine constants.
            begin
            {DATA}
            end procedure;""")

        if prototype_only:
            return template.splitlines()[0][:-3] + ';'
        data = [x._pyha_reset_constants() for x in self.data.elems]
        return template.format(DATA=formatter(data))

    def build_update_registers(self, prototype_only=False):
        template = textwrap.dedent("""\
            procedure pyha_update_registers(self:inout self_t) is
                -- loads 'next' values to registers, executed on clock rising edge
            begin
            {DATA}
            end procedure;""")

        if prototype_only:
            return template.splitlines()[0][:-3] + ';'
        data = [x._pyha_update_registers() for x in self.data.elems]
        return template.format(DATA=formatter(data))

    def build_init(self, prototype_only=False):
        template = textwrap.dedent("""\
            procedure pyha_init_next(self:inout self_t) is
                -- sets all .next's to current register values, executed before 'main'. 
                -- thanks to this, '.next' variables are always written before read, so they can never be registers
            begin
            {DATA}
            end procedure;""")

        if prototype_only:
            return template.splitlines()[0][:-3] + ';'
        data = [x._pyha_init() for x in self.data.elems]
        return template.format(DATA=formatter(data))

    def build_data_structs(self):
        template = textwrap.dedent("""\
            type next_t is record
            {DATA}
            end record;
            
            type self_t is record
            {DATA}
                \\next\\: next_t;
            end record;""")

        data = [f'{x._pyha_name()}: {x._pyha_type()};' for x in self.data.elems]
        return template.format(DATA=formatter(data))

    def build_typedefs(self):
        # self typedefs
        typedefs = [x._pyha_typedef() for x in self.data.elems if x._pyha_typedef() is not None]

        # local vars
        for function in self.value:
            if not isinstance(function, DefNodeVHDL):
                continue
            variables = [init_vhdl_type(name, val, val) for name, val in function.data.locals.items()]
            typedefs += [x._pyha_typedef() for x in variables if x._pyha_typedef() is not None]
        typedefs = list(dict.fromkeys(typedefs))  # get rid of duplicates
        return typedefs

    def build_package_header(self):
        template = textwrap.dedent("""\
            {MULTILINE_COMMENT}
            package {NAME} is
            {SELF_T}
            {SELF_ARRAY_TYPEDEF}

            {FUNC_HEADERS}
            end package;""")

        sockets = {}
        sockets['MULTILINE_COMMENT'] = self.multiline_comment
        sockets['SELF_ARRAY_TYPEDEF'] = \
            f'    type {self.data._pyha_arr_type_name()} is array (natural range <>) of {self.data._pyha_type()};'
        sockets['NAME'] = self.data._pyha_module_name()
        sockets['SELF_T'] = tabber(self.build_data_structs())

        proto = '\n'.join(x.build_function(prototype_only=True) for x in self.value if isinstance(x, DefNodeVHDL))
        proto += '\n\n-- internal pyha functions\n'
        proto += self.build_update_registers(prototype_only=True) + '\n'
        proto += self.build_reset(prototype_only=True) + '\n'
        proto += self.build_init(prototype_only=True) + '\n'
        proto += self.build_reset_constants(prototype_only=True) + '\n'
        proto += self.build_deepcopy(prototype_only=True) + '\n'
        proto += self.build_list_deepcopy(prototype_only=True) + '\n'
        sockets['FUNC_HEADERS'] = tabber(proto)

        return template.format(**sockets)

    def build_package_body(self):
        template = textwrap.dedent("""\
            package body {NAME} is
            {USER_FUNCTIONS}
            
            {RESET_SELF}
            
            {UPDATE_SELF}
            
            {INIT_SELF}
            
            {CONSTANT_SELF}
            
            {DEEPCOPY}
            
            {DEEPCOPY_LIST}

            end package body;""")

        sockets = {}
        sockets['NAME'] = self.data._pyha_module_name()

        sockets['INIT_SELF'] = tabber(self.build_init())
        sockets['CONSTANT_SELF'] = tabber(self.build_reset_constants())
        sockets['RESET_SELF'] = tabber(self.build_reset())
        sockets['DEEPCOPY'] = tabber(self.build_deepcopy())
        sockets['DEEPCOPY_LIST'] = tabber(self.build_list_deepcopy())
        sockets['UPDATE_SELF'] = tabber(self.build_update_registers())
        sockets['USER_FUNCTIONS'] = '\n\n'.join(tabber(str(x)) for x in self.value if isinstance(x, DefNodeVHDL))

        return template.format(**sockets)

    def __str__(self):
        template = textwrap.dedent("""\
            {FILE_HEADER}
            {IMPORTS}

            {PACKAGE_HEADER}

            {PACKAGE_BODY}
            """)

        sockets = {}
        sockets['FILE_HEADER'] = file_header()
        sockets['IMPORTS'] = self.build_imports()
        sockets['PACKAGE_HEADER'] = self.build_package_header()
        sockets['PACKAGE_BODY'] = self.build_package_body()
        return template.format(**sockets)


def redbaron_node_to_vhdl_node(red: Node, caller):
    """ Convert RedBaron class to conversion class
    For example: red:NameNode returns NameNodeVHDL class
    """
    import sys

    red_type = red.__class__.__name__
    try:
        cls = getattr(sys.modules[__name__], red_type + 'VHDL')
    except AttributeError:
        if red_type == 'NoneType':
            return None
        raise

    return cls(red_node=red, parent=caller)


convert_obj = None


def set_convert_obj(obj):
    global convert_obj
    convert_obj = obj


def convert(red: Node, obj=None):
    set_convert_obj(obj)

    # delete all non convertable functions from redbaron AST
    while True:
        f = red.find('def', name=lambda x: x in SKIP_FUNCTIONS or x[:2] == '__' or x[:5] == '_pyha')
        if not f:
            break
        f.parent.remove(f)

    # run RedBaron based conversions before parsing
    red = CallModifications.apply(red)
    if obj is not None:
        red = EnumModifications.apply(red)
        ImplicitNext.apply(red)
    red = ForModification.apply(red)
    if obj is not None:
        AutoResize.apply(red)
        SubmoduleDeepcopy.apply(red)
        SubmoduleListDeepcopy.apply(red)

    conv = redbaron_node_to_vhdl_node(red, caller=None)  # converts all nodes

    return conv


#################### FUNCTIONS THAT MODIFY REDBARON AST #############
#####################################################################
#####################################################################
#####################################################################
#####################################################################
#####################################################################


def super_getattr(obj, attr):

    for part in attr.split('.'):
        if part == 'self' or part == 'next':
            continue

        if part.find('[') != -1:  # is array indexing
            part = part[:part.find('[')]
            obj = getattr(obj, part)[0]  # just take first array element, because the index may be variable
        elif part.find(']') != -1:
            # this can happen if array index includes '.' so arr.split makes false split. example: self.a[self.b]
            continue
        else:
            obj = getattr(obj, part)

    return obj


class AutoResize:
    """ Auto resize on Sfix assignments
     Examples (depend on initial Sfix type):
         self.sfix_reg = a        ->   self.sfix_reg = resize(a, 5, -29, fixed_wrap, fixed_round)
         self.sfix_list[0] = a    ->   self.sfix_list[0] = resize(a, 0, 0, fixed_saturate, fixed_round)
         """

    @staticmethod
    def find(red_node):
        """ Find all assignments that are subject to auto resize conversion """

        def is_subject(x):
            """
            Acceptable examples:
                    self.a = b
                    self.a.b = a
                    self.b[0] = a
                    self.a[3].b.b = a
            """
            if len(x) > 1 and str(x[0].value) == 'self':
                return True
            return False

        return red_node.find_all('assign', target=is_subject)

    @staticmethod
    def filter(nodes):
        """ Resize stuff should happen on Sfix registers only, filter others out """

        passed_nodes = []
        types = []
        for x in nodes:
            t = super_getattr(convert_obj, str(x.target))
            if isinstance(t, Sfix):
                passed_nodes.append(x)
                types.append(t)
        return passed_nodes, types

    @staticmethod
    def apply(red_node):
        """ Wrap all subjects to autosfix inside resize() according to initial type """
        nodes = AutoResize.find(red_node)

        pass_nodes, pass_types = AutoResize.filter(nodes)
        for node, var_t in zip(pass_nodes, pass_types):

            if isinstance(node.value, (FloatNode, IntNode)) \
                    or (isinstance(node.value, UnitaryOperatorNode) and isinstance(node.value.target, (FloatNode, IntNode))): # second term to pass marked(-) nodes, like -1. -0.34 etc
                node.value = f'Sfix({node.value}, {var_t.left}, {var_t.right})'
            else:
                node.value = f'resize({node.value}, {var_t.left}, {var_t.right}, fixed_{var_t.overflow_style}, fixed_{var_t.round_style})'

        return pass_nodes


class SubmoduleDeepcopy:
    """ Converts assign to submodule to 'pyha_deepcopy' call"""
    @staticmethod
    def apply(red_node):
        nodes = AutoResize.find(red_node)

        for x in nodes:
            target_type = init_vhdl_type('-', super_getattr(convert_obj, str(x.target)))
            if isinstance(target_type, VHDLModule):
                x.replace(
                    f'{target_type._pyha_module_name()}.pyha_deepcopy({str(x.target).replace(".next","")}, {str(x.value)})')


class SubmoduleListDeepcopy:

    @staticmethod
    def apply(red_node):
        nodes = AutoResize.find(red_node)

        for x in nodes:
            target_type = init_vhdl_type('-', super_getattr(convert_obj, str(x.target)))
            if isinstance(target_type, VHDLList) and not target_type.not_submodules_list:
                x.replace(
                    f'{target_type.elems[0]._pyha_module_name()}.pyha_list_deepcopy({str(x.target).replace(".next","")}, {str(x.value)})')


class ImplicitNext:
    """
    On all assignments add 'next' before the final target. This is to support variable based signal assignment in VHDL code.

    Examples:
    self.a -> self.next.a
    self.a[i] -> self.next.a[i]
    self.submod.a -> self.submod.next.a
    self.submod.a[i].a -> self.submod.a[i].next.a

    self.a, self.b = call() -> self.next.a, self.next.b = call()

    Special case, when ComplexSfix: NOT IMPLEMENTED
    self.complx.real -> self.next.complx.real

    """

    @staticmethod
    def apply(red_node):

        def add_next(x):
            if len(x) > 1 and str(x[0].value) == 'self':
                loc = len(x) - 1
                if isinstance(x[loc], GetitemNode):
                    loc -= 1
                x.insert(loc, 'next')

        assigns = red_node.find_all('assign')
        for node in assigns:
            if isinstance(node.target, TupleNode):
                for mn in node.target:
                    add_next(mn)
            else:
                add_next(node.target)


class CallModifications:

    @staticmethod
    def neww(red_node):

        is_hack = False

        # make sure each created variable is unique by appending this number and incrementing
        tmp_var_count = 0

        # loop over all atomtrailers, call is always a member of this
        atomtrailers = red_node.find_all('atomtrailers')
        for i, atom in enumerate(atomtrailers): # reversed is for the case when one call is argument to other
            if is_hack: # when parsed out of order call
                atom = atomtrailers[i - 1]
                call = atom.call
                is_hack = False
            else:
                call = atom.call # this actually points to the stuff between ()

            if call is None: # this atomtrailer has no function call
                continue

            if call.call is not None: # one of the arguments is a call -> process it first (i expect it is next in the list)
                atom = atomtrailers[i+1]
                call = atom.call
                is_hack = True

                if call is None: # this atomtrailer has no function call
                    continue

            call_index = call.previous.index_on_parent
            if call_index == 0: # input is something like x() -> len(), Sfix() ....
                continue

            # get the TARGET function object from datamodel
            target_func_name = atom.copy()
            del target_func_name[call_index+1:]
            target_func_obj = super_getattr(convert_obj, str(target_func_name))

            # set prefix as first argument (self)
            # self.d(a) -> d(self, a)
            prefix = atom.copy()
            del prefix[call_index:]
            del atom[:call_index]
            call.insert(0, prefix)

            # get the SOURCE (where call is going on) function object from datamodel
            def_parent = atom.parent_find('def')
            source_func_name = f'self.{def_parent.name}'
            source_func_obj = super_getattr(convert_obj, str(source_func_name))

            # if call is not to local class function
            # self.moving_average.main(x) -> MODULE_NAME.main(self.moving_average, x)
            if str(prefix) != 'self':
                var = super_getattr(convert_obj, str(prefix))
                var = init_vhdl_type('-', var, var)
                red_node.insert(0, var._pyha_module_name())

            if target_func_obj.last_return is None:
                continue # function is not returning stuff -> this is simple
            else:

                # add return variables to function locals, so that they will be converted to VHDL variables
                ret_vars = []
                for x in get_iterable(target_func_obj.last_return):
                    name = f'pyha_ret_{tmp_var_count}'
                    ret_vars.append(name)
                    source_func_obj.locals[name] = x # add var to SOURCE function
                    tmp_var_count += 1

                    # add return variable to arguments
                    call.append(name)
                    # call.value[-1].target = f'ret_{j}'


                # need to add new source line before the CURRENT line..search for the node with linenodes
                line_node = atom
                while type(line_node.next) != EndlNode:
                    line_node = line_node.parent

                # add function call BEFORE the CURRENT line
                line_node.parent.insert(line_node.index_on_parent, atom.copy())
                atom.replace(','.join(ret_vars))

        return red_node

    @staticmethod
    def transform_prefix(red_node):
        """
        Main work is to add 'self' argument to function call
        self.d(a) -> d(self, a)

        If function owner is not exactly 'self' then 'unknown_type' is prepended.
        self.next.moving_average.main(x) -> unknown_type.main(self.next.moving_average, x)

        self.d(a) -> d(self, a)
        self.next.d(a) -> d(self.next, a)
        local.d() -> type.d(local)
        self.local.d() -> type.d(self.local)

        """

        def modify_call(red_node):
            call_args = red_node.find('call')
            i = call_args.previous.index_on_parent
            if i == 0:
                return red_node  # input is something like a()

            if isinstance(red_node.parent, AssertNode):
                return red_node
            prefix = red_node.copy()
            del prefix[i:]
            del red_node[:i]

            # this happens when 'redbaron_pyfor_to_vhdl' does some node replacements
            if isinstance(prefix.value, DotProxyList) and len(prefix) == 1:
                prefix = prefix[0]

            call_args.insert(0, prefix)
            if prefix.dumps() not in ['self', 'self.next']:
                var = super_getattr(convert_obj, prefix.dumps())
                var = init_vhdl_type('-', var, var)
                red_node.insert(0, var._pyha_module_name())
                # v = VHDLType(str(prefix[-1]), red_node=prefix)
                # red_node.insert(0, v.var_type)

        atoms = red_node.find_all('atomtrailers')
        for i, x in enumerate(atoms):
            if x.call is not None:
                modify_call(x)

        return red_node

    @staticmethod
    def transform_returns(red_node):
        """
        Convert function calls, that return into variable into VHDL format.
        b = self.a(a) ->
            self.a(a, ret_0=b)

        self.next.b[0], self.next.b[1] = self.a(self.a) ->
            self.a(self.a, ret_0=self.next.b[0], ret_1=self.next.b[1])

        """

        def modify_call(x: AssignmentNode):
            try:
                if str(x.value[0]) != 'self':  # most likely call to 'resize' no operatons needed
                    if str(x.value[0][0]) != 'self':  # this is some shit that happnes after 'for' transforms
                        return x
            except:
                return x

            call = x.call
            # dont run this function for calls to len()
            if call.previous.value == 'len':
                return x

            if len(x.target) == 1 or isinstance(x.target, AtomtrailersNode):
                call.append(str(x.target))
                call.value[-1].target = 'ret_0'
            else:
                for j, argx in enumerate(x.target):
                    call.append(str(argx))
                    call.value[-1].target = f'ret_{j}'
            return x.value

        assigns = red_node.find_all('assign')
        for x in assigns:
            if x.call is not None:
                new = modify_call(x.copy())
                x.replace(new)
        return red_node

    @staticmethod
    def apply(red_node):
        red_node = CallModifications.neww(red_node)
        # red_node = CallModifications.transform_returns(red_node)
        # red_node = CallModifications.transform_prefix(red_node)
        return red_node


class ForModification:
    @staticmethod
    def apply(red_node):
        def modify_for(red_node):
            # if for range contains call to 'range' -> skip
            with suppress(Exception):
                if red_node.target('call')[0].previous.value == 'range':
                    return red_node

            ite = red_node.iterator
            red_node(ite.__class__.__name__, value=ite.value) \
                .map(lambda x: x.replace(f'{red_node.target}[_i_]'))

            red_node.iterator = '_i_'
            return red_node

        fors = red_node.find_all('for')
        for x in fors:
            modify_for(x)

        return red_node


class EnumModifications:
    """
    Converts 'EnumType.ENUMVALUE' to integer value , see #154
    """

    @staticmethod
    def apply(red_node):

        data = VHDLModule('-', convert_obj)
        enums = [x for x in data.elems if isinstance(x, VHDLEnum)]
        for x in enums:
            type_name = x._pyha_type()
            red_names = red_node.find_all('atomtrailers', value=lambda x: x[0].value == type_name)
            for i, node in enumerate(red_names):
                enum_obj = type(x.current)[str(node[1])]
                red_names[i].replace(str(enum_obj.value))

        return red_node
