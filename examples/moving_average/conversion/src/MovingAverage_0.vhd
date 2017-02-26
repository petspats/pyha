-- generated by pyha 0.0.0 at 2017-02-25 18:56:56
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;
    use ieee.fixed_float_types.all;
    use ieee.fixed_pkg.all;
    use ieee.math_real.all;

library work;
    use work.ComplexTypes.all;
    use work.PyhaUtil.all;
    use work.all;


package MovingAverage_0 is

    type sfixed0_17_list_t is array (natural range <>) of sfixed(0 downto -17);

    type next_t is record
        window_len: integer;
        shift_register: sfixed0_17_list_t(0 to 7);
        sum: sfixed(3 downto -17);
    end record;

    type self_t is record
        -- constants
        window_pow: integer;
        \_delay\: integer;

        window_len: integer;
        shift_register: sfixed0_17_list_t(0 to 7);
        sum: sfixed(3 downto -17);
        \next\: next_t;
    end record;

    procedure \_pyha_constants_self\(self: inout self_t);

    procedure \_pyha_reset_self\(self: inout self_t);

    procedure \_pyha_update_self\(self: inout self_t);

    -- Hardware model of moving average
    procedure main(self:inout self_t; x: sfixed(0 downto -17); ret_0:out sfixed(0 downto -17));
end package;

package body MovingAverage_0 is
    procedure \_pyha_constants_self\(self: inout self_t) is
    begin
        self.window_pow := 3;
        self.\_delay\ := 1;

    end procedure;

    procedure \_pyha_reset_self\(self: inout self_t) is
    begin
        self.\next\.window_len := 8;
        self.\next\.shift_register := (Sfix(0.0, 0, -17), Sfix(0.0, 0, -17), Sfix(0.0, 0, -17), Sfix(0.0, 0, -17), Sfix(0.0, 0, -17), Sfix(0.0, 0, -17), Sfix(0.0, 0, -17), Sfix(0.0, 0, -17));
        self.\next\.sum := Sfix(0.0, 3, -17);
        \_pyha_update_self\(self);
    end procedure;

    procedure \_pyha_update_self\(self: inout self_t) is
    begin
        self.window_len := self.\next\.window_len;
        self.shift_register := self.\next\.shift_register;
        self.sum := self.\next\.sum;
        \_pyha_constants_self\(self);
    end procedure;

    -- Hardware model of moving average
    procedure main(self:inout self_t; x: sfixed(0 downto -17); ret_0:out sfixed(0 downto -17)) is
        variable nsum: sfixed(5 downto -17);
        variable ret: sfixed(0 downto -17);
    begin

        -- add new element to shift register
        self.\next\.shift_register := x & self.shift_register(0 to self.shift_register'high-1);

        -- calculate new sum
        nsum := self.sum + x - self.shift_register(self.shift_register'length-1);

        -- resize sum, overflow is impossible
        self.\next\.sum := resize(nsum, left_index=>self.window_pow + left_index(x), right_index=>right_index(x), overflow_style=>fixed_wrap);

        -- divide sum by amout of window_len, and resize to same format as input 'x'
        ret := resize(self.sum sra self.window_pow, size_res=>x);
        ret_0 := ret;
        return;
    end procedure;
end package body;
