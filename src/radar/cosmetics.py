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
    def format(self, obj, context, maxlevels, level):
        if isinstance(obj, np.ndarray) and obj.ndim > 1:
            return self.format_array(obj), True, False
        return super().format(obj, context, maxlevels, level)

    def format_array(self, array):
        array_str = np.array2string(
            array, separator=", ", precision=2, suppress_small=True, formatter={"float_kind": lambda x: f"{x:.2f}"}
        )
        indented_lines = self.indent_lines(array_str, str(array.dtype))
        return indented_lines

    def indent_lines(self, array_str, dtype_str):
        lines = array_str.split("\n")
        indented_lines = ["array(" + lines[0]]
        for line in lines[1:]:
            indented_lines.append(" " * 25 + line)
        indented_lines[-1] = indented_lines[-1] + f", dtype={dtype_str})"
        return "\n".join(indented_lines)
