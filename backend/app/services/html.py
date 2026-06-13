from html import escape


def source_to_html(source: str) -> str:
    clean_source = source if source.strip() else "[No source code returned]"
    return (
        '<pre class="generated-code"><code>'
        + escape(clean_source)
        + "</code></pre>"
    )


def message_to_html(message: str, css_class: str = "assistant-message") -> str:
    return f'<div class="{escape(css_class)}">{escape(message)}</div>'

