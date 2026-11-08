"""Haq: chat UI.  Run: streamlit run app.py"""
import streamlit as st
from lawyer.bot import Session, turn
from lawyer.llm import LLM, PRESETS
from lawyer.checker import KB

st.set_page_config(page_title="Haq: help with deposits and refunds", layout="wide")

with st.sidebar:
    st.header("Model")
    provider = st.selectbox("Provider", ["groq", "gemini", "openrouter", "custom"])
    model = st.text_input("Model (blank = default)", placeholder=PRESETS[provider][1])
    key_env = PRESETS[provider][2]
    try:
        secret_key = st.secrets.get(key_env, "")
    except Exception:
        secret_key = ""
    api_key = st.text_input("API key", type="password", help="Blank = use the key saved in the app's secrets.") or secret_key
    base_url = st.text_input("Base URL") if provider == "custom" else None

if "session" not in st.session_state:
    st.session_state.session, st.session_state.msgs = Session(), []
S: Session = st.session_state.session

st.title("Haq")
st.caption("Free help when a landlord won't return your deposit, or a seller won't give a refund. "
           "This is legal information, not legal advice, and Haq is not a lawyer. Don't share Aadhaar, bank passwords or OTPs.")

with st.sidebar:
    st.header("Your case")
    c = S.case
    if c.get("type") not in (None, "", "unknown"):
        st.markdown(f"**Type:** {c.get('type')}  \n**Amount:** {c.get('amount') or '?'}  \n"
                    f"**Other party:** {c.get('other_party') or '?'}  \n**Place:** {c.get('state_city') or '?'}")
        for label, key in (("Facts", "facts"), ("You have", "evidence_have"), ("Still needed", "evidence_missing"),
                           ("Open questions", "open_questions")):
            if c.get(key):
                st.markdown(f"**{label}:**\n" + "\n".join(f"- {x}" for x in c[key]))
        if c.get("timeline"):
            st.markdown("**Timeline:**\n" + "\n".join(f"- {t.get('date','?')}: {t.get('event','')}" for t in c["timeline"]
                                                      if isinstance(t, dict)))
    else:
        st.write("Tell Haq what happened. Your case card will build up here.")
    st.divider()
    col1, col2 = st.columns(2)
    draft_btn = col1.button("Draft notice", disabled=S.mode == "roleplay")
    rp_btn = col2.button("Stop practice" if S.mode == "roleplay" else "Practise talking")
    if st.button("Start over"):
        st.session_state.session, st.session_state.msgs = Session(), []
        st.rerun()
    st.caption(f"Laws Haq may cite: {len(KB['laws'])}, each checked by a human (last checked {KB['verified_on']}). "
               "Any other legal reference is removed automatically.")


def render(m):
    if m["role"] == "user":
        st.chat_message("user").write(m["content"])
        return
    t = m["turn"]
    with st.chat_message("assistant"):
        if t.get("mode") == "roleplay":
            st.markdown(f"🎭 **{S.case.get('other_party') or 'Other party'}:** {t['reply']}")
            if t.get("coach"):
                st.info(f"Coach: {t['coach']}")
        else:
            st.markdown(t["reply"])
        ref = t.get("referral") or {}
        if ref.get("needed"):
            st.warning("**Please talk to a lawyer or legal aid.** " + " ".join(ref["reasons"]) + "\n\n" +
                       "\n".join(f"- **{r['name']}**: {r['how']}" for r in ref["resources"]))
        if t.get("draft"):
            st.markdown("**Draft (check every [placeholder] before sending):**")
            st.code(t["draft"], language=None)
            st.download_button("Download draft", t["draft"], "notice.txt", key=f"dl{id(m)}")
        if t.get("citations"):
            with st.expander(f"Laws referred to ({len(t['citations'])}), with text from Haq's verified list"):
                for l in t["citations"]:
                    st.markdown(f"**{l['title']}**: {l['plain']}" + (f"  \n*Caution: {l['caution']}*" if l["caution"] else "")
                                + f"  \n<small>Source: {l['official_source']}</small>", unsafe_allow_html=True)
        removed = (t.get("audit") or {}).get("removed") or []
        if removed:
            st.caption(f"⚠️ Haq's checker removed {len(removed)} legal reference(s) it could not verify.")


for m in st.session_state.msgs:
    render(m)


def run_turn(text, action=None):
    if not api_key:
        st.error(f"Add an API key in the sidebar (free Gemini key: aistudio.google.com/apikey).")
        st.stop()
    llm = LLM(provider, model or None, api_key=api_key, base_url=base_url)
    if text:
        st.session_state.msgs.append({"role": "user", "content": text})
    with st.spinner("Thinking..."):
        try:
            t = turn(S, llm, text or "", action)
        except Exception as e:
            st.error(f"The model call failed: {e}")
            st.stop()
    st.session_state.msgs.append({"role": "assistant", "turn": t})
    st.rerun()


if draft_btn:
    run_turn("", "draft")
if rp_btn:
    run_turn("", "roleplay_stop" if S.mode == "roleplay" else "roleplay_start")
prompt = st.chat_input("Practise: reply to the other party..." if S.mode == "roleplay"
                       else "Describe your problem, e.g. 'My landlord hasn't returned my Rs 30,000 deposit'")
if prompt:
    run_turn(prompt)
