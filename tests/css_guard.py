"""The page-CSS guard: what a stylesheet under tokens/pages/ may and may not say, and its twin for markup.

`page_css_violations(css)` returns one string per problem, so [] means the sheet is clean. It is used by
tests/test_tokens.py (every sheet in the folder, plus the guard's own tests) and by any page test that
wants to check one sheet. Task 9's pages add their own sheets and are covered as soon as they exist.
`markup_colour_violations(markup)` is the same rule for the pages and templates themselves: no raw colour
in a style attribute, a drawing attribute or a <style> block (tests/test_markup_colours.py).

Banned in a page sheet:
  - a raw colour: hex, rgb(), hsl(), hwb(), lab(), lch(), oklab(), oklch(), color(), or a CSS named colour;
  - a literal font family, in `font-family` or in the `font` shorthand;
  - a raw font size, in `font-size` or in the `font` shorthand: a size is a step of the type scale;
  - a colour in a data: URI, other than the black and white a mask needs (below);
  - a declaration of any custom property that tokens.css defines (`--font-serif: Georgia`, `--ground: ...`,
    `--space-4: ...`), and an `@property` rule naming one. A page asks for a token with var(); only
    tokens.css gives it a value, so a page cannot recolour or re-type the system by redefining a name.
    A page may make custom properties of its own. Custom property names are case sensitive.
Allowed:
  - `transparent`, `currentColor` and the CSS-wide keywords;
  - a font family only as a `var(--font-...)` token that tokens.css defines, so a page can ask for the
    serif or mono role and tokens.css decides the family;
  - a font size only as a step of the scale, in one of three forms:
        var(--fs-body)                              one step;
        clamp(var(--fs-lead), 2.8vw, var(--fs-h3))  two steps with any length between them: the viewport sets
                                                    the pace, the steps set the floor and the ceiling;
        min(var(--fs-h1), var(--fs-h2))             min() or max() whose every argument is a step.
    Every bound is a step, so no size can leave the scale. Refused: calc() as a size, a clamp() whose lower or
    upper bound is anything but a step (`clamp(var(--fs-small), 2vw, 40vw)`), a min() or max() with a length
    in it (`max(var(--fs-small), 5vw)`), a bare `5vw`, and any rem, px, em or % size.
NOT checked: the other lengths. Spacing, widths, line heights and letter-spacing may be raw in a page sheet.
`--space-*` is preferred, not enforced.

A data: URI is the one place a colour hides from the value scan below, so it is read: an SVG one (plain or
base64) is parsed and may hold only black, white and `none`, because a mask is luminance and not a design
colour. Any other data: URI is refused, because it cannot be read for colours. Move it to an asset file.

Only declaration values are read. Comments, strings and url() count as nothing, so a class called .red or
a content string is fine. Standard library only.
"""
import base64
import binascii
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

TOKENS = (Path(__file__).resolve().parents[1] / "tokens" / "tokens.css").read_text(encoding="utf-8")
ROOT_BLOCK = re.search(r":root\s*\{(.*?)\}", TOKENS, re.S).group(1)

DECLARED_TOKENS = frozenset(re.findall(r"(--[\w-]+)\s*:", ROOT_BLOCK))   # every custom property tokens.css defines
FONT_TOKENS = frozenset(name for name in DECLARED_TOKENS if name.startswith("--font-"))   # the family tokens
SIZE_TOKENS = frozenset(name for name in DECLARED_TOKENS if name.startswith("--fs-"))      # the type-scale steps

# The 148 named colours of CSS Color 4. `transparent` and `currentcolor` are not here, on purpose.
NAMED_COLOURS = frozenset("""
    aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown
    burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
    darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
    darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet
    deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro
    ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow
    lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray
    lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine
    mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise
    mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab
    orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru
    pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen
    seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan teal thistle
    tomato turquoise violet wheat white whitesmoke yellow yellowgreen
""".split())
COLOUR_FUNCTIONS = re.compile(r"(?<![\w-])(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(", re.I)
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
CSS_WIDE = frozenset({"inherit", "initial", "unset", "revert", "revert-layer"})
# Words a `font` shorthand may hold besides sizes, line heights and the family: style, variant, weight, stretch, size.
FONT_KEYWORDS = frozenset(
    "normal italic oblique small-caps bold bolder lighter ultra-condensed extra-condensed condensed "
    "semi-condensed semi-expanded expanded extra-expanded ultra-expanded xx-small x-small small medium "
    "large x-large xx-large xxx-large smaller larger".split()
)
NUMBER_OR_LENGTH = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)[a-z%]*", re.I)
DECLARATION = re.compile(r"(?<![\w-])(?P<prop>[\w-]+)\s*:\s*(?P<value>[^;{}]*?)\s*(?=[;}])")
SIMPLE_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*\)")
# What the middle of a clamp() may be made of: any length. min, max, clamp and calc in nesting, commas and
# operators, var(), numbers with any unit. Nothing else (no url(), no strings).
LENGTH_FUNCTIONS = frozenset({"clamp", "min", "max", "calc"})
LENGTH_PIECE = re.compile(
    r"\s*(?:(?P<var>var\(\s*(?P<name>--[\w-]+)\s*\))|(?P<fn>[a-z-]+)\(|(?P<close>\))|(?P<comma>,)"
    r"|(?P<op>[*/+-])|(?P<num>[+-]?(?:\d+\.?\d*|\.\d+)(?P<unit>[a-z%]*)))", re.I)
# Words a `font` shorthand may hold before the size: style, variant, weight (a bare number) and stretch.
FONT_BEFORE_SIZE = frozenset(
    "normal italic oblique small-caps bold bolder lighter ultra-condensed extra-condensed condensed "
    "semi-condensed semi-expanded expanded extra-expanded ultra-expanded".split()
)
# A drawing attribute that carries a colour, and the colour words a mask may keep. A mask is luminance.
COLOUR_ATTRIBUTES = frozenset({"fill", "stroke", "stop-color", "flood-color", "lighting-color", "color"})
MASK_COLOURS = frozenset({"#fff", "#ffffff", "#000", "#000000", "white", "black", "none", "transparent", "currentcolor", "inherit"})
DATA_URL = re.compile(
    r"""url\(\s*(?:"(?P<dq>(?:\\.|[^"\\])*)"|'(?P<sq>(?:\\.|[^'\\])*)'|(?P<bare>[^)'"\s]*))\s*\)""", re.I)
AT_PROPERTY = re.compile(r"@property\s+(--[\w-]+)")


def top_level(value, separators):
    """Split a value on the separator characters that sit outside parentheses, dropping empty pieces."""
    pieces, depth, current = [], 0, ""
    for char in value:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0 and char in separators:
            pieces.append(current)
            current = ""
        else:
            current += char
    return [piece.strip() for piece in pieces + [current] if piece.strip()]


def family_problems(value, where, families):
    """`font-family` and the family part of `font`: only var(--font-...) tokens that tokens.css defines."""
    found = []
    for item in top_level(value, ","):
        match = SIMPLE_VAR.fullmatch(item)
        if not (match and match.group(1) in families):
            found.append(f"{where}: {item!r} is not a font family token defined in tokens.css (use var(--font-...))")
    return found


def font_shorthand_problems(value, families):
    """`font: [style weight] size[/line-height] family`. Every word must be a number, a length, a known
    keyword, a function (calc, clamp), a var() of a token tokens.css defines, and the family a font token."""
    if value.lower() in CSS_WIDE:
        return []
    found, family_seen = font_size_problems(font_shorthand_size(value), "font"), False
    for word in top_level(value, " \t\n/,"):
        var = SIMPLE_VAR.fullmatch(word)
        if var:
            if var.group(1) in families:
                family_seen = True
            elif var.group(1) not in DECLARED_TOKENS:
                found.append(f"font: {word} is not a token defined in tokens.css")
        elif not (NUMBER_OR_LENGTH.fullmatch(word) or word.lower() in FONT_KEYWORDS
                  or re.fullmatch(r"(?:calc|clamp|min|max)\(.*\)", word, re.I | re.S)):
            found.append(f"font: {word!r} is a literal, not a size or a font family token (use var(--font-...))")
    if not found and not family_seen:
        found.append(f"font: {value!r} names no font family token (use var(--font-...))")
    return found


def font_shorthand_size(value):
    """The size word of a `font` shorthand: the first word after the style, weight and stretch words,
    before any `/line-height`. A shorthand with no size has none, so what stands there is named."""
    for word in top_level(value, " \t\n"):
        head = (top_level(word, "/") or [word])[0]
        if head.lower() in FONT_BEFORE_SIZE or re.fullmatch(r"\d{1,4}", head):
            continue
        return head
    return ""


def function_call(value):
    """(name, [argument, ...]) when `value` is exactly one function call, else None. Arguments are split on
    the commas outside nested parentheses, and an empty piece is dropped, so `clamp(a,,c)` has two."""
    head = re.match(r"([a-z-]+)\(", value, re.I)
    if not head:
        return None
    depth = 0
    for index in range(head.end() - 1, len(value)):
        depth += {"(": 1, ")": -1}.get(value[index], 0)
        if depth == 0:
            if index != len(value) - 1:
                return None                                           # something follows the call
            return head.group(1).lower(), top_level(value[head.end():index], ",")
    return None                                                       # the parentheses never close


def is_step(argument):
    """Whether `argument` is exactly var() of a type-scale step that tokens.css defines."""
    match = SIMPLE_VAR.fullmatch(argument.strip())
    return bool(match) and match.group(1) in SIZE_TOKENS


def length_problems(expression):
    """What is wrong with the middle of a clamp(): anything that is not a length expression."""
    found, depth, position = [], 0, 0
    while position < len(expression):
        piece = LENGTH_PIECE.match(expression, position)
        if not piece or piece.end() == position:
            return found + [f"{expression[position:].strip()!r} is not a length"]
        position = piece.end()
        if piece["fn"]:
            depth += 1
            if piece["fn"].lower() not in LENGTH_FUNCTIONS:
                found.append(f"{piece['fn']}() is not a length function")
        elif piece["close"]:
            depth -= 1
            if depth < 0:
                return found + ["the parentheses do not balance"]
    return found + (["the parentheses do not balance"] if depth else [])


def size_problems(value):
    """Why `value` is not a step of the scale, one string per reason; [] if it is one of the three forms."""
    var = SIMPLE_VAR.fullmatch(value)
    if var:
        return [] if var.group(1) in SIZE_TOKENS else [f"{var.group(1)} is not a type-scale step defined in tokens.css"]
    call = function_call(value)
    if call is None:
        return ["it is a raw size" if value else "there is no size"]
    name, args = call
    if name == "clamp":
        if len(args) != 3:
            return ["clamp() needs three arguments: a step, a length and a step"]
        found = [f"the {label} bound {arg} is not a type-scale step" for label, arg in (("lower", args[0]), ("upper", args[2]))
                 if not is_step(arg)]
        return found + [f"the middle of clamp() {item}" for item in length_problems(args[1])]
    if name in ("min", "max"):
        if not args:
            return [f"{name}() has no arguments"]
        return [f"{name}() argument {arg} is not a type-scale step" for arg in args if not is_step(arg)]
    if name == "calc":
        return ["calc() is not a font size"]
    return [f"{name}() is not a size function"]


def font_size_problems(value, where):
    """A font size is a step of the scale (see the module docstring for the three forms). `where` is the
    property the size sits in."""
    value = re.sub(r"\s*!important$", "", value.strip(), flags=re.I)
    if value.lower() in CSS_WIDE:
        return []
    return [f"{where}: {value or '(none)'} {problem}: use var(--fs-...) from tokens.css, or clamp(var(--fs-...), length, var(--fs-...))"
            for problem in size_problems(value)]


def colour_problems(value, where):
    """Raw colours in one declaration value. A var()'s token name is taken out (it is never a colour), but a
    fallback after the comma stays, so var(--ink, #fff) is caught."""
    bare = re.sub(r"var\(\s*--[\w-]+\s*(?=[,)])", "(", value)
    found = [f"{where}: raw colour {m.group(0)}" for m in HEX_COLOUR.finditer(bare)]
    found += [f"{where}: raw colour function {m.group(0)}" for m in COLOUR_FUNCTIONS.finditer(bare)]
    found += [f"{where}: named colour {word}" for word in re.findall(r"(?<![\w-])[A-Za-z]+(?![\w-])", bare)
              if word.lower() in NAMED_COLOURS]
    return found


def redefinition(name, where):
    """The one message for a page that gives a value to a name tokens.css owns."""
    return f"{where}: redefines {name}, which tokens.css defines (change it there; a page only reads it with var({name}))"


def page_css_violations(css, families=FONT_TOKENS):
    """Everything in a page stylesheet that breaks the rule above. Comments, strings and url() are read as
    nothing, and only declaration values are scanned, so a class called .red or a content string is fine."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = data_url_problems(css)                                       # read before strings and url() are blanked
    css = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", '""', css)   # a string stays visible as ""
    css = re.sub(r"url\([^)]*\)", "url()", css)
    found += [redefinition(name, "@property " + name) for name in AT_PROPERTY.findall(css) if name in DECLARED_TOKENS]
    for declaration in DECLARATION.finditer(css):
        name = declaration.group("prop")                                 # custom properties are case sensitive
        prop, value = name.lower(), re.sub(r"\s*!important$", "", declaration.group("value"), flags=re.I)
        where = f"{prop}: {value}"
        if name in DECLARED_TOKENS:
            found.append(redefinition(name, where))
        if prop == "font-family":
            found += [] if value.lower() in CSS_WIDE else family_problems(value, prop, families)
        elif prop == "font":
            found += font_shorthand_problems(value, families)
        elif prop == "font-size":
            found += font_size_problems(value, prop)
        found += colour_problems(value, where)
    return found




def data_url_problems(css):
    """Every data: URI in `css` read for colours. An SVG one (plain or base64) holds only a mask's black and
    white; any other kind cannot be read, so it is refused."""
    found = []
    for match in DATA_URL.finditer(css):
        uri = match.group("dq") or match.group("sq") or match.group("bare") or ""
        if not uri.lower().startswith("data:"):
            continue
        head, _, payload = uri.partition(",")
        kind = head[5:].split(";")[0].strip().lower() or "text/plain"
        if kind != "image/svg+xml":
            found.append(f"url(data:{kind}): a {kind} data URI cannot be read for colours: use an SVG, or move it to an asset file")
            continue
        try:
            markup = base64.b64decode(unquote(payload), validate=True).decode("utf-8") if ";base64" in head.lower() else unquote(payload)
        except (binascii.Error, ValueError):
            found.append("url(data:image/svg+xml): the data URI is not valid, so it cannot be read for colours")
            continue
        found += [f"url(data:image/svg+xml): {item}" for item in markup_colour_violations(markup, masked=True)]
    return found


class _MarkupColours(HTMLParser):
    """One pass over markup: every colour in a style attribute, a drawing attribute or a <style> block.
    Inside a <mask> only black and white (and none) are kept, because there colour is luminance."""

    def __init__(self, masked):
        super().__init__(convert_charrefs=True)
        self.floor = self.mask = 1 if masked else 0
        self.found, self.sheet = [], None

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            self.attribute(tag, name.lower(), value or "")
        if tag == "mask":
            self.mask += 1
        elif tag == "style":
            self.sheet = []

    def handle_endtag(self, tag):
        if tag == "mask" and self.mask > self.floor:
            self.mask -= 1
        elif tag == "style" and self.sheet is not None:
            self.found += [f"<style>: {item}" for item in page_css_violations("".join(self.sheet))]
            self.sheet = None

    def handle_data(self, data):
        if self.sheet is not None:
            self.sheet.append(data)

    def attribute(self, tag, name, value):
        if name == "style":
            if self.mask:
                for declaration in value.split(";"):
                    prop, _, setting = declaration.partition(":")
                    if prop.strip().lower() in COLOUR_ATTRIBUTES and not self.mask_colour(setting):
                        self.found.append(f'<{tag}> style="{value}": {setting.strip()} is not black or white (a mask is luminance)')
            else:
                self.found += [f'<{tag}> style="{value}": {item}' for item in page_css_violations("a{" + value + "}")]
        elif name in COLOUR_ATTRIBUTES:
            where = f'<{tag}> {name}="{value}"'
            if self.mask:
                if not self.mask_colour(value):
                    self.found.append(f"{where}: not black or white (a mask is luminance)")
            else:
                self.found += colour_problems(re.sub(r"url\([^)]*\)", "url()", value), where)

    @staticmethod
    def mask_colour(value):
        return re.sub(r"\s*!important$", "", value.strip().lower()) in MASK_COLOURS


def markup_colour_violations(markup, masked=False):
    """Raw colours in `markup`, one string per finding, [] if clean. `masked` treats the whole markup as the
    inside of a mask: how a data: URI's SVG is read."""
    scan = _MarkupColours(masked)
    scan.feed(markup)
    scan.close()
    return list(dict.fromkeys(scan.found))
