import re
import html
import streamlit as st
from difflib import SequenceMatcher
import streamlit.components.v1 as components

def normalize(text):
    # Normalise all curly quotes, apostrophes, and ellipses for comparison
    return (
        text
        .replace('“', '"').replace('”', '"')
        .replace('‘', "'").replace('’', "'")
        .replace('…', '...')
        .replace('\u00A0', ' ')  # non-breaking space to normal space
        .lower()
    )

def unify_quotes(text):
    # For HTML data attributes: keep visible text identical
    return (
        text
        .replace('“', '"').replace('”', '"')
        .replace('‘', "'").replace('’', "'")
        .replace('…', '...')
    )

def tokenize(text):
    # Treat ellipsis as punctuation; split on words, whitespace, or punctuation
    text = text.replace('...', ' … ')  # temp marker
    tokens = re.findall(r'\w+|\s+|…|[^\w\s]', text)
    # Restore to '...' if needed, but treat as punctuation (not as a word)
    result = []
    for t in tokens:
        if t == '…':
            result.append('...')
        else:
            result.append(t)
    return result

def is_word(token):
    # Only pure words (no punctuation or ellipsis)
    return re.fullmatch(r'\w+', token) is not None

def loose_equal(a, b):
    # Compare, ignoring trailing punctuation, ellipsis, quotes, etc.
    def clean(token):
        t = normalize(token)
        t = re.sub(r'[^\w]+$', '', t)  # remove non-word at end
        return t
    return clean(a) == clean(b)

st.set_page_config(layout="wide")
st.title("Quote Checker")

# ─── Inputs ────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.subheader("Source material")
    src_raw = st.text_area("", height=300, key="src")
with col2:
    st.subheader("Final article")
    art_raw = st.text_area("", height=300, key="art")

# ─── Index source sentences ────────────────────────────────────────────────
sent_split_re = re.compile(r'(?<=[\.!?])(\s+)')
src_lines = src_raw.split('\n')
global_sents = []
global_norm_sents = []
line_to_sents = []

for line in src_lines:
    parts = re.split(sent_split_re, line)
    idxs = []
    i = 0
    while i < len(parts):
        sent = parts[i]
        if sent:
            idx = len(global_sents)
            global_sents.append(sent)
            global_norm_sents.append(normalize(sent))
            idxs.append(idx)
        i += 2
    line_to_sents.append(idxs)

body_text = " ".join(global_sents)
src_toks = tokenize(normalize(body_text))

# ─── Build output_html with highlighted spans ─────────────────────────────
quote_re = re.compile(r'“[^”]+”|"[^"]+"')
matches = list(quote_re.finditer(art_raw))

THRESHOLD, MIN_EQ_RUN = 0.5, 2
errors, out_parts, last_i = 0, [], 0

for m in matches:
    a, b = m.span()
    raw_q = m.group(0)
    open_q, close_q = raw_q[0], raw_q[-1]
    content = raw_q[1:-1]

    subs = re.split(r'(?<=[\.!?])(\s+)', content)
    temp = []
    for i in range(0, len(subs), 2):
        sent = subs[i]
        ws = subs[i+1] if i+1 < len(subs) else ""

        raw_toks = tokenize(sent)
        norm_toks = [normalize(t) if is_word(t) else t for t in raw_toks]
        n = len(norm_toks)
        total_w = sum(1 for t in raw_toks if is_word(t))
        short_q = total_w <= 1

        # align
        best_r, best_i = 0.0, 0
        for j in range(max(1, len(src_toks)-n+1)):
            r = SequenceMatcher(None, norm_toks, src_toks[j:j+n]).ratio()
            if r > best_r:
                best_r, best_i = r, j

        # colour tokens
        highlighted = []
        window = src_toks[best_i:best_i+n]
        matcher = SequenceMatcher(None, norm_toks, window)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            seg = raw_toks[i1:i2]
            # index of first word in this segment (in the quote)
            abs_start = i1
            abs_end = i2
            for k, w in enumerate(seg):
                abs_pos = abs_start + k
                is_last = (abs_pos == len(raw_toks) - 1) and is_word(w)
                if tag == 'equal':
                    wc = sum(1 for w2 in seg if is_word(w2))
                    if short_q or wc >= MIN_EQ_RUN:
                        phrase = "".join(seg)
                        highlighted.append(f"<span style='background:#c8e6c9'>{phrase}</span>")
                        break  # Only need to add once
                    else:
                        if is_word(w):
                            highlighted.append(f"<span style='background:#ffcdd2'>{w}</span>")
                            errors += 1
                        else:
                            highlighted.append(w)
                else:
                    if is_word(w):
                        if is_last:
                            # Try to match loosely with last token in the window
                            # Check all tokens in window, in a small window (+/-2)
                            match_found = False
                            for off in range(-2, 3):
                                src_idx = j2 - 1 + off
                                if 0 <= src_idx < len(window):
                                    if loose_equal(w, window[src_idx]):
                                        highlighted.append(f"<span style='background:#c8e6c9'>{w}</span>")
                                        match_found = True
                                        break
                            if not match_found:
                                highlighted.append(f"<span style='background:#ffcdd2'>{w}</span>")
                                errors += 1
                        else:
                            highlighted.append(f"<span style='background:#ffcdd2'>{w}</span>")
                            errors += 1
                    else:
                        highlighted.append(w)

        # map to source sentence index
        qn = normalize(sent)
        if any(qn in s for s in global_norm_sents):
            sid = next(i for i, s in enumerate(global_norm_sents) if qn in s)
        else:
            sid = max(
                range(len(global_norm_sents)),
                key=lambda i: SequenceMatcher(None, qn, global_norm_sents[i]).ratio()
            )

        # wrap each green chunk
        for chunk in highlighted:
            if "background:#c8e6c9" in chunk:
                inner = re.sub(r'<.*?>(.*?)</.*?>', r'\1', chunk)
                phrase = html.escape(inner)
                temp.append(
                    f'<span data-sent="{sid}" '
                    f'      data-phrase="{phrase}" '
                    f'      style="background:#c8e6c9;cursor:pointer">'
                    f'{phrase}</span>'
                )
            else:
                temp.append(chunk)

        temp.append(html.escape(ws))

    out_parts.append(html.escape(art_raw[last_i:a]))
    out_parts.append(open_q + "".join(temp) + close_q)
    last_i = b

out_parts.append(html.escape(art_raw[last_i:]))
output_html = "".join(out_parts)

# ─── Build reference HTML ─────────────────────────────────────────────────
ref_lines_html = []
for li, line in enumerate(src_lines):
    idxs = line_to_sents[li]
    parts = re.split(sent_split_re, line)
    j, line_html = 0, ""
    for sid in idxs:
        sent_raw = parts[j]
        spc = parts[j+1] if j+1 < len(parts) else ""
        j += 2

        lead = sent_raw[0] if sent_raw and sent_raw[0] in '"“”‘’' else ""
        trail = sent_raw[-1] if sent_raw and sent_raw[-1] in '"“”‘’' else ""
        core = sent_raw
        if lead: core = core[1:]
        if trail: core = core[:-1]

        upcore = unify_quotes(core)
        escaped = html.escape(upcore)

        line_html += (
            f'{html.escape(lead)}'
          + f'<span class="ref-sent" data-sent="{sid}" data-original="{escaped}">'
          + escaped
          + '</span>'
          + f'{html.escape(trail)}'
          + html.escape(spc)
        )

    if not idxs:
        line_html = html.escape(unify_quotes(line))

    ref_lines_html.append(f'<div class="ref-line" style="font-family:Arial,sans-serif">{line_html}</div>')

ref_html = "\n".join(ref_lines_html)

# ─── Status banner ─────────────────────────────────────────────────────────
status = (
    '<span style="color:green">All quotes correct</span>'
    if errors == 0 else
    '<span style="color:red">Misquotes present</span>'
)

# ─── Final HTML + CSS + JS ────────────────────────────────────────────────
html_template = """
<style>
  #reference, #output, #status {
    font-family: Arial, sans-serif;
  }
  #reference [data-sent].highlight { background: #c8e6c9; }

  /* status styling */
  #status {
    font-size: 0.85em;
  }
</style>

<div style="display:flex; gap:30px;">
  <div style="flex:1;">
    <h3 style="font-family:Arial,sans-serif;">Reference</h3>
    <div id="reference" style="max-height:600px; overflow:auto;">
      @@REF@@
    </div>
  </div>
  <div style="flex:1;">
    <div style="display:flex; justify-content: space-between; align-items: center;">
      <h3 style="font-family:Arial,sans-serif; margin:0;">Output</h3>
      <span id="status">@@STATUS@@</span>
    </div>
    <button id="copy-output">Copy Output</button>
    <div id="output"
         style="white-space:pre-wrap; max-height:600px; overflow:auto;">
@@ART@@</div>
  </div>
</div>

<script>
  // copy plain text
  document.getElementById('copy-output').addEventListener('click', async () => {
    const text = document.getElementById('output').innerText;
    try {
      await navigator.clipboard.writeText(text);
      const btn = document.getElementById('copy-output');
      const old = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(()=> btn.textContent = old, 1500);
    } catch(e) {
      console.error(e);
    }
  });

  // click-to-highlight/bold
  document.getElementById('output').addEventListener('click', e => {
    const tok = e.target.closest('[data-phrase]');
    if (!tok) return;
    const phrase = tok.dataset.phrase;
    const sid    = tok.dataset.sent;
    const refPane= document.getElementById('reference');

    // clear old
    refPane.querySelectorAll('[data-sent].highlight')
           .forEach(el=>el.classList.remove('highlight'));
    refPane.querySelectorAll('b')
           .forEach(b=>b.replaceWith(document.createTextNode(b.textContent)));

    // highlight sentence
    const refSent = refPane.querySelector('[data-sent="'+sid+'"]');
    if (!refSent) return;
    refSent.classList.add('highlight');

    // bold exactly that phrase
    const orig = refSent.dataset.original;
    const rexp = new RegExp('(' + phrase.replace(/[-\\/\\\\^$*+?.()|[\\]{}]/g,'\\\\$&') + ')','i');
    refSent.innerHTML = orig.replace(rexp, '<b>$1</b>');
    refSent.scrollIntoView({behavior:'smooth', block:'center'});
  });
</script>
"""

html_code = (
    html_template
      .replace('@@REF@@',    ref_html)
      .replace('@@ART@@',    output_html)
      .replace('@@STATUS@@', status)
)

components.html(html_code, height=750, scrolling=True)
