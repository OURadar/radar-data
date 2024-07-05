#
#   Created by Boonleng Cheong
#

import pprint
import numpy as np

colors = {
    "red": 196,
    "orange": 214,
    "yellow": 227,
    "green": 118,
    "mint": 43,
    "teal": 87,
    "cyan": 14,
    "blue": 33,
    "pink": 170,
    "purple": 141,
    "white": 15,
    "gray": 239,
    "black": 232,
}

highlights = {"warning": "\033[48;5;172;38;5;15m", "error": "\033[1;48;5;3;38;5;15m"}


def colorize(text, color="white", end="\033[m"):
    if isinstance(color, int):
        return f"\033[38;5;{color}m{text}{end}"
    elif color in colors:
        num = colors[color]
        return f"\033[38;5;{num}m{text}{end}"
    elif color in highlights:
        code = highlights[color]
        return f"{code}{text}{end}"
    else:
        return text


def hex2rgba(strs):
    for str in strs:
        r = int(str[:2], 16) / 255
        g = int(str[2:4], 16) / 255
        b = int(str[4:6], 16) / 255
        print(f"[{r:.3f}, {g:.3f}, {b:.3f}, 1.0]")


def color_name_value(name, value):
    show = colorize(name, "orange")
    show += colorize(" = ", "red")
    show += colorize(value, "yellow" if isinstance(value, str) else "purple")
    return show


def byte_string(payload):
    lower_bound = int.from_bytes(b"\x20", "big")
    upper_bound = int.from_bytes(b"\x73", "big")
    count = 0
    bound = min(25, len(payload))
    for s in bytes(payload[:bound]):
        if lower_bound <= s <= upper_bound:
            count += 1
    if len(payload) < 30:
        return f"{payload}"
    if count > bound / 2:
        return f"{payload[:25]} ... {payload[-5:]}"
    else:

        def payload_binary(payload):
            h = [f"{d:02x}" for d in payload]
            return "[." + ".".join(h) + "]"

        p = f"{payload[0:1]}"
        return p + payload_binary(payload[1:8]) + " ... " + payload_binary(payload[-3:])


class NumpyPrettyPrinter(pprint.PrettyPrinter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_indent = 0

    def format(self, obj, context, maxlevels, level):
        if isinstance(obj, np.ndarray) and obj.ndim > 1:
            return self.format_2d_array(obj), True, False
        return super().format(obj, context, maxlevels, level)

    def format_2d_array(self, array):
        if isinstance(array, np.ma.MaskedArray):
            data_str = np.array2string(
                array.data,
                separator=", ",
                suppress_small=True,
                formatter={"float_kind": lambda x: " -----" if x == array.fill_value else f"{x:6.2f}"},
            )
            if isinstance(array.mask, np.ndarray):
                mask_str = np.array2string(
                    array.mask,
                    separator=", ",
                    formatter={"bool": lambda x: "  True" if x else " False"},
                )
            else:
                mask_str = repr(array.mask)
            prefix = "array_2d("
            indented_lines = self.indent_lines(data_str, prefix + "data=")
            indented_lines += ",\n" + " " * self._current_indent
            indented_lines += self.indent_lines(mask_str, " " * len(prefix) + "mask=", array.data.dtype, array.fill_value)
        else:
            array_str = np.array2string(array, separator=", ", suppress_small=True, formatter={"float_kind": lambda x: f"{x:6.2f}"})
            indented_lines = self.indent_lines(array_str, "array_2d(", array.dtype)
        return indented_lines

    def indent_lines(self, array_str, prefix, dtype=None, fill_value=None):
        lines = array_str.split("\n")
        indented_lines = [prefix + lines[0]]
        indent = " " * (self._current_indent + len(prefix))
        for line in lines[1:]:
            indented_lines.append(indent + line)
        if fill_value:
            indent = indent[:-5]
            indented_lines[-1] += ","
            indented_lines.append(f"{indent}fill_value={str(fill_value)}")
            if dtype:
                indented_lines[-1] += ","
                indented_lines.append(f"{indent}dtype={str(dtype)})")
        elif dtype:
            indented_lines[-1] += f", dtype={str(dtype)})"
        return "\n".join(indented_lines)

    def _format_dict_items(self, items, stream, indent, allowance, context, level):
        write = stream.write
        indent += self._indent_per_level
        delimnl = ",\n" + " " * indent
        last_index = len(items) - 1
        for i, (key, ent) in enumerate(items):
            if isinstance(ent, np.ndarray) and ent.ndim > 1:
                indent = level * self._indent_per_level
                self._current_indent = indent + len(repr(key)) + 2
                if i == 0:
                    write("\n" + " " * indent)
                delimnl = ",\n" + " " * indent
                write(f"{repr(key)}: {self.format_2d_array(ent)}")
                if i == last_index:
                    write("\n" + " " * indent)
            else:
                self._current_indent = indent + len(repr(key)) + 2
                write(f"{repr(key)}: ")
                self._format(ent, stream, indent + len(repr(key)) + 2, allowance if i == last_index else 1, context, level)
            if i != last_index:
                write(delimnl)
