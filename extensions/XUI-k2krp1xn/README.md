# Markdown Preview Validation - UI Extension UPDATED

Tests for `fenced_code`, `codehilite`, `tables`, `nl2br`, `sane_lists`, and `footnotes`.

## 1. Basic Markdown

### Text Formatting

Regular text, **bold text**, *italic text*, and ***bold italic text***.

Inline code: `print("Hello, world!")`

Escaped characters: \*literal asterisks\*.

### Links

[Visit GitHub](https://github.com)

[Reference-style link][example]

[example]: https://example.com "Example website"

### Blockquote

> This is a blockquote.
>
> This is another paragraph inside the blockquote.

### Horizontal Rule

---

## 2. Fenced Code — fenced_code

Expected: each example appears in a code block and preserves indentation.

### No Language Specified

```
Plain text code block.
    This line has four leading spaces.
**This should remain literal text.**
<div>This should not become an HTML element.</div>
```

### Tilde Fence

~~~text
This block uses tildes instead of backticks.
Whitespace and line breaks should be preserved.
~~~

### Backticks Inside a Code Block

```text
Inline code syntax: `example`
Markdown heading syntax: # Example
```

## 3. Syntax Highlighting — codehilite

Expected: language keywords, strings, comments, and numbers have distinct styles when highlighting CSS is loaded.

### Python

```python
# Example comment
def greet(name: str, count: int = 3) -> None:
    for index in range(count):
        print(f"Hello, {name}! Visit {index + 1}")

greet("Karl")
```

### JavaScript

```javascript
// Example comment
const values = [1, 2, 3];

function double(value) {
  return value * 2;
}

console.log(values.map(double));
```

### JSON

```json
{
  "enabled": true,
  "name": "Markdown preview",
  "count": 3,
  "features": ["code", "tables", "footnotes"],
  "optional": null
}
```

### Bash

```bash
# Example comment
preview_name="Markdown"
echo "Testing ${preview_name}"
git status --short
```

### Diff

```diff
- enabled = False
+ enabled = True
```

## 4. Tables — tables

Expected: a table with left, center, and right column alignment.

| Left aligned | Center aligned | Right aligned |
| :--- | :---: | ---: |
| Alpha | Active | 10 |
| Beta | Pending | 250 |
| Gamma | Complete | 1,000 |

### Formatting Inside Cells

| Feature | Example |
| --- | --- |
| Bold | **Bold text** |
| Italic | *Italic text* |
| Inline code | `example_value` |
| Link | [Example](https://example.com) |
| Escaped pipe | Left \| Right |
| Empty cell | |

## 5. Automatic Line Breaks — nl2br

Expected: the following three source lines appear on three separate rendered lines, although they belong to one paragraph.
There are no trailing spaces or backslashes on these lines.
This is the third line.

This is a new paragraph after a blank line.
This is the second line of the new paragraph.

### Line Breaks Inside a Blockquote

> First quoted line.
> Second quoted line.
> Third quoted line.

### Explicit Line Breaks

This line ends with two spaces.  
This should appear on the next line.

## 6. List Behavior — sane_lists

### Unordered List

- First item
- Second item
- Third item

### Ordered List

1. First step
2. Second step
3. Third step

### Ordered List Starting at Four

Expected: the rendered numbering begins at 4.

4. Fourth step
5. Fifth step
6. Sixth step

### Unordered Marker Inside an Ordered List

Expected: the bullet does not turn into another numbered item.
Without a blank line, it remains continuation text in the second item.

1. Ordered item one
2. Ordered item two
* This marker should remain continuation text.

### Ordered Marker Inside an Unordered List

Expected: the numbered marker does not turn into another bullet.
Without a blank line, it remains continuation text in the second item.

- Unordered item one
- Unordered item two
1. This marker should remain continuation text.

### Separate Lists With a Blank Line

Expected: an unordered list followed by a separate ordered list.

- Unordered item A
- Unordered item B

1. Ordered item A
2. Ordered item B

### Nested Lists

- Parent item A
    - Child item A1
    - Child item A2
- Parent item B
    1. Ordered child B1
    2. Ordered child B2

### Multiple Paragraphs in a List Item

1. First paragraph of the first item.

    Second paragraph of the first item.

2. Second item.

## 7. Footnotes — footnotes

This sentence references a simple footnote.[^simple]

This sentence references a footnote with formatting.[^formatted]

This sentence references a footnote with multiple paragraphs.[^long]

Here is another reference to the same simple footnote.[^simple]

[^simple]: This is a simple footnote.

[^formatted]: This footnote contains **bold text**, *italic text*, and a [link](https://example.com).

[^long]: This is the first paragraph of the longer footnote.

    This is the second paragraph. It should remain inside the same footnote.

## 8. Combined Features

### Table With a Footnote

| Extension | Purpose |
| --- | --- |
| `fenced_code` | Fenced code blocks |
| `codehilite` | Syntax highlighting[^highlighting] |
| `tables` | Markdown tables |
| `nl2br` | Automatic line breaks |
| `sane_lists` | Consistent list behavior |
| `footnotes` | References and footnote definitions |

[^highlighting]: Visible syntax colors require Pygments and matching highlighting CSS.

### List With Line Breaks and Inline Formatting

1. This item contains **bold text**.
    This line continues the same item.
2. This item contains `inline code`.
    This line also continues the same item.

## Validation Checklist

- Fenced code blocks preserve indentation and literal text.
- Language-specific code blocks show syntax colors.
- Tables render with the requested alignment.
- Ordinary single newlines produce visible line breaks.
- The ordered list starting at 4 displays 4, 5, and 6.
- Mixed list markers behave as described.
- Nested lists preserve their hierarchy.
- Footnote references link to their definitions.
- Footnotes provide links back to their references.