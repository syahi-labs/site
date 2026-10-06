"""The page-CSS guard: what a stylesheet under tokens/pages/ may and may not say.

`page_css_violations(css)` returns one string per problem, so [] means the sheet is clean. It is used by
tests/test_tokens.py (every sheet in the folder, plus the guard's own tests) and by any page test that
wants to check one sheet. Task 9's pages add their own sheets and are covered as soon as they exist.

Banned in a page sheet:
  - a raw colour: hex, rgb(), hsl(), hwb(), lab(), lch(), oklab(), oklch(), color(), or a CSS named colour;
  - a literal font family, in `font-family` or in the `font` shorthand;
  - a declaration of any custom property that tokens.css defines (`--font-serif: Georgia`, `--ground: ...`,
    `--space-4: ...`), and an `@property` rule naming one. A page asks for a token with var(); only
    tokens.css gives it a value, so a page cannot recolour or re-type the system by redefining a name.
    A page may make custom properties of its own. Custom property names are case sensitive.
Allowed:
  - `transparent`, `currentColor` and the CSS-wide keywords;
  - a font family only as a `var(--font-...)` token that tokens.css defines, so a page can ask for the
    serif or mono role and tokens.css decides the family.
NOT checked: lengths. A raw font size, spacing or line height is allowed in a page sheet. `--fs-*` and
`--space-*` are preferred, not enforced.

Only declaration values are read. Comments, strings and url() count as nothing, so a class called .red or
a content string is fine. Standard library only.
"""
import re
from pathlib import Path

TOKENS = (Path(__file__).resolve().parents[1] / "tokens" / "tokens.css").read_text(encoding="utf-8")
ROOT_BLOCK = re.search(r":root\s*\{(.*?)\}", TOKENS, re.S).group(1)

DECLARED_TOKENS = frozenset(re.findall(r"(--[\w-]+)\s*:", ROOT_BLOCK))   # every custom property tokens.css defines
FONT_TOKENS = frozenset(name for name in DECLARED_TOKENS if name.startswith("--font-"))   # the family tokens

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
    found, family_seen = [], False
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
    css = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", '""', css)   # a string stays visible as ""
    css = re.sub(r"url\([^)]*\)", "url()", css)
    found = [redefinition(name, "@property " + name) for name in AT_PROPERTY.findall(css) if name in DECLARED_TOKENS]
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
        found += colour_problems(value, where)
    return found


