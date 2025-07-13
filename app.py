import re
import html
import streamlit as st
from difflib import SequenceMatcher
import streamlit.components.v1 as components

def normalize(text):
    return (
        text
        .replace('“','"').replace('”','"')
        .replace("‘","'").replace("’","'")
        .lower()
    )

def unify_quotes(text):
    return (
        text
        .replace('“','"').replace('”','"')
        .replace("‘","'").replace("’","'")
    )

def tokenize(text):
    return re.findall(r'\w+|\s+|[^\w\s]', text)

# ─── Page setup ────────────────────────────────────────────────────────────
st.set_page_config(layout="wide")
st.title("Quote Checker")

# ─── Inputs with Arial headings ────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.markdown(
        '<h4 style="margin:0 0 0.25rem; font-family:Arial,sans-serif;">'
        'Source material</h4>',
        unsafe_allow_html=True
    )
    src_raw = st.text_area("", height=300, key="src")
with col2:
    st.markdown(
        '<h4 style="margin:0 0 0.25rem; font-family:Arial,sans-serif;">'
        'Final article</h4>',
        unsafe_allow_html=True
    )
    art_raw = st.text_area("", height=300, key="art")

# ─── Normalize mid-sentence line breaks in source ─────────────────────────
raw_lines = src_raw.split("\n")
merged, buf = [], ""
for line in raw_lines:
    s = line.strip()
    if not s:
        if buf:
            merged.append(buf); buf = ""
        continue
    buf = (buf + " " + s) if buf else s
    if re.search(r'[\.!?](?:["’”])?$', s) or s.endswith("/ENDS"):
        merged.append(buf); buf = ""
if buf: merged.append(buf)
src_lines = merged

# ─── Index source sentences ────────────────────────────────────────────────
sent_split_re     = re.compile(r'(?<=[\.!?])(\s+)')
global_sents      = []
global_norm_sents = []
line_to_sents     = []

for line in src_lines:
    parts = re.split(sent_split_re, line)
    idxs, i = [], 0
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
src_toks   = tokenize(normalize(body_text))

# ─── Extract, align & colourize quotes ────────────────────────────────────
quote_re = re.compile(r'“[^”]+”|"[^"]+"')
matches  = list(quote_re.finditer(art_raw))

THRESHOLD, MIN_EQ_RUN = 0.5, 2
errors, out_parts, last_i = 0, [], 0

for m in matches:
    a, b    = m.span()
    raw_q   = m.group(0)
    open_q, close_q = raw_q[0], raw_q[-1]
    content = raw_q[1:-1]

    subs = re.split(r'(?<=[\.!?])(\s+)', content)
    frag = []
    for i in range(0, len(subs), 2):
        sent = subs[i]
        ws   = subs[i+1] if i+1 < len(subs) else ""
        raw_toks  = tokenize(sent)
        norm_toks = [normalize(t) if re.fullmatch(r'\w+',t) else t for t in raw_toks]
        n         = len(norm_toks)
        total_w   = sum(1 for t in raw_toks if re.fullmatch(r'\w+',t))
        short_q   = (total_w <= 1)

        # find best alignment
        best_r, best_i = 0, 0
        for j in range(max(1, len(src_toks)-n+1)):
            r = SequenceMatcher(None, norm_toks, src_toks[j:j+n]).ratio()
            if r > best_r:
                best_r, best_i = r, j

        highlighted = []
        if best_r < THRESHOLD:
            for t in raw_toks:
                if re.fullmatch(r'\w+',t):
                    highlighted.append(f"<span style='background:#ffcdd2'>{t}</span>")
                    errors += 1
                else:
                    highlighted.append(t)
        else:
            window  = src_toks[best_i:best_i+n]
            matcher = SequenceMatcher(None, norm_toks, window)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                seg = raw_toks[i1:i2]
                if tag == 'equal':
                    wc = sum(1 for w in seg if re.fullmatch(r'\w+',w))
                    if short_q or wc >= MIN_EQ_RUN:
                        phrase = "".join(seg)
                        highlighted.append(f"<span style='background:#c8e6c9'>{phrase}</span>")
                    else:
                        for w in seg:
                            if re.fullmatch(r'\w+',w):
                                highlighted.append(f"<span style='background:#ffcdd2'>{w}</span>")
                                errors += 1
                            else:
                                highlighted.append(w)
                else:
                    for w in seg:
                        if re.fullmatch(r'\w+',w):
                            highlighted.append(f"<span style='background:#ffcdd2'>{w}</span>")
                            errors += 1
                        else:
                            highlighted.append(w)

        # map back to source sentence
        qn = normalize(sent)
        if any(qn in s for s in global_norm_sents):
            sid = next(i for i,s in enumerate(global_norm_sents) if qn in s)
        else:
            sid = max(
                range(len(global_norm_sents)),
                key=lambda i: SequenceMatcher(None, qn, global_norm_sents[i]).ratio()
            )

        # wrap each green fragment as clickable
        for chunk in highlighted:
            if "background:#c8e6c9" in chunk:
                inner  = re.sub(r'<.*?>(.*?)</.*?>', r'\1', chunk)
                phrase = html.escape(inner)
                frag.append(
                    f'<span data-sent="{sid}" data-phrase="{phrase}" '
                    f'style="background:#c8e6c9;cursor:pointer">{phrase}</span>'
                )
            else:
                frag.append(chunk)
        frag.append(html.escape(ws))

    out_parts.append(html.escape(art_raw[last_i:a]))
    out_parts.append(open_q + "".join(frag) + close_q)
    last_i = b

out_parts.append(html.escape(art_raw[last_i:]))
output_html = "".join(out_parts)

# ─── Build Reference panel HTML ────────────────────────────────────────────
ref_lines_html = []
for li, line in enumerate(src_lines):
    idxs  = line_to_sents[li]
    parts = re.split(sent_split_re, line)
    j, line_html = 0, ""
    for sid in idxs:
        sent_raw = parts[j]
        spc      = parts[j+1] if j+1 < len(parts) else ""
        j       += 2

        lead  = sent_raw[0] if sent_raw and sent_raw[0] in '"“”‘’' else ""
        trail = sent_raw[-1] if sent_raw and sent_raw[-1] in '"“”‘’' else ""
        core  = sent_raw[1:-1] if (lead and trail) else sent_raw
        upcore  = unify_quotes(core)
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

    ref_lines_html.append(
        f'<div style="font-family:Arial,sans-serif; margin-bottom:0.2em;">'
        f'{line_html}</div>'
    )

ref_html = "\n".join(ref_lines_html)

# ─── Status banner ─────────────────────────────────────────────────────────
status = (
    '<span style="color:green;font-family:Arial,sans-serif;">All quotes correct</span>'
    if errors == 0 else
    '<span style="color:red;font-family:Arial,sans-serif;">Misquotes present</span>'
)

# ─── Final HTML + CSS + JS ─────────────────────────────────────────────────
html_template = """
<style>
  /* Use Arial for all headings, text, status, buttons */
  h3, #reference, #output, #status, button {
    font-family: Arial, sans-serif;
  }
  #reference [data-sent].highlight { background:#c8e6c9; }
  #status { font-size:0.85em; }
</style>

<div style="display:flex; gap:30px;">
  <div style="flex:1;">
    <h3 style="margin-bottom:0.5em;">Reference</h3>
    <div id="reference" style="max-height:600px; overflow:auto; padding-right:1em;">
      @@REF@@
    </div>
  </div>

  <div style="flex:1;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
      <h3 style="margin:0;">Output</h3>
      <span id="status">@@STATUS@@</span>
    </div>
    <button id="copy-output" style="margin-bottom:0.5rem;">Copy Output</button>
    <div id="output" style="white-space:pre-wrap; max-height:600px; overflow:auto; padding-right:1em;">@@ART@@</div>
  </div>
</div>

<script>
  // Copy plain text
  document.getElementById('copy-output').addEventListener('click', async () => {
    const txt = document.getElementById('output').innerText;
    await navigator.clipboard.writeText(txt);
    const btn = document.getElementById('copy-output'), old = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(()=> btn.textContent = old, 1500);
  });

  // Click-to-highlight & bold
  document.getElementById('output').addEventListener('click', e => {
    const tok = e.target.closest('[data-phrase]');
    if (!tok) return;
    const phrase = tok.dataset.phrase;
    const sid    = tok.dataset.sent;
    const refPg  = document.getElementById('reference');

    // clear old
    refPg.querySelectorAll('[data-sent].highlight')
         .forEach(el => el.classList.remove('highlight'));
    refPg.querySelectorAll('b')
         .forEach(b => b.replaceWith(document.createTextNode(b.textContent)));

    // highlight sentence
    const refSent = refPg.querySelector('[data-sent="'+sid+'"]');
    if (!refSent) return;
    refSent.classList.add('highlight');

    // bold exact phrase
    const orig = refSent.dataset.original;
    const rexp = new RegExp('('+phrase.replace(/[-\\/\\\\^$*+?.()|[\\]{}]/g,'\\\\$&')+')','i');
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
