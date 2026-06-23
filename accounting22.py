import os
import tempfile
import difflib

import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from fpdf import FPDF

st.set_page_config(page_title="Accounting By A/C", layout="wide", page_icon="📊")

# =====================================================================================
#  CORE DATA LOGIC  —  UNCHANGED (do not modify the business logic below)
# =====================================================================================

def safe_float(value):
    try:
        # აშორებს ყველაფერს ციფრისა და წერტილის გარდა (მაგ: (1,200.50) -> 1200.50)
        cleaned = str(value).replace('(', '').replace(')', '').replace(',', '').strip()
        return float(cleaned)
    except:
        return 0.0


def is_name_similar(name1, name2):
    n1, n2 = str(name1).strip().lower(), str(name2).strip().lower()
    return difflib.SequenceMatcher(None, n1, n2).ratio() > 0.90


def match_phone(row, phone_df):
    debt_val = safe_float(row.get('ვალები', 0))
    if debt_val <= 0:
        return "", ""

    target_name = str(row['სახელი გვარი']).strip()
    p_nomeri = str(row['პირადი ნომერი']).strip()
    matches = phone_df[phone_df['სახელი გვარი'].apply(lambda x: is_name_similar(x, target_name))]

    if matches.empty:
        return "ნომერი ვერ მოიძებნა", ""
    if len(matches) == 1:
        sh_val = str(matches.iloc[0].get('შენიშვნა', ''))
        return matches.iloc[0]['ტელეფონი'], "" if sh_val.lower() == 'nan' else sh_val

    for length in [11, 7, 4]:
        if len(p_nomeri) >= length:
            suffix = p_nomeri[-length:]
            sub_match = matches[matches['პირადი ნომერი'].astype(str).str.endswith(suffix)]
            if not sub_match.empty:
                sh_val = str(sub_match.iloc[0].get('შენიშვნა', ''))
                return sub_match.iloc[0]['ტელეფონი'], "" if sh_val.lower() == 'nan' else sh_val
    return "დუბლიკატია", ""


# =====================================================================================
#  PDF DESIGN SYSTEM  —  corporate palette, typography helpers, chart generation
# =====================================================================================

COLOR_PRIMARY = (44, 62, 80)        # Deep Slate
COLOR_MUTED = (127, 140, 141)       # Muted grey-blue for secondary text
COLOR_DEBT = (192, 57, 43)          # Soft Crimson
COLOR_DEBT_LIGHT = (250, 235, 233)
COLOR_ADVANCE = (39, 116, 85)       # Emerald / Sage
COLOR_ADVANCE_LIGHT = (232, 245, 238)
COLOR_LIGHT_BG = (246, 247, 248)
COLOR_ZEBRA = (249, 250, 250)
COLOR_BORDER = (222, 226, 229)
COLOR_HEADER_BG = (44, 62, 80)
COLOR_WHITE = (255, 255, 255)

FONT_REGULAR_PATH = "dejavu-sans.book.ttf"
FONT_BOLD_CANDIDATES = ["dejavu-sans.bold.ttf", "DejaVuSans-Bold.ttf", "dejavusans-bold.ttf"]


def _font_prop_for_matplotlib():
    """Loads the same Georgian-capable font for chart labels, if present."""
    if os.path.exists(FONT_REGULAR_PATH):
        try:
            return fm.FontProperties(fname=FONT_REGULAR_PATH)
        except Exception:
            return None
    return None


def generate_debt_chart(sum_df):
    """Horizontal bar chart of top projects by total debt. Returns a temp PNG path."""
    font_prop = _font_prop_for_matplotlib()
    top = sum_df.sort_values('ვალი', ascending=False).head(8).iloc[::-1]

    fig, ax = plt.subplots(figsize=(7.6, 3.4), dpi=200)
    max_val = top['ვალი'].max() if len(top) else 0
    bar_colors = ["#C0392B" if v == max_val else "#D98C82" for v in top['ვალი']]

    bars = ax.barh(top['პროექტი'], top['ვალი'], color=bar_colors, height=0.55, zorder=3)

    ax.set_title("ტოპ პროექტები ვალის მიხედვით", fontproperties=font_prop,
                 fontsize=13, color="#2C3E50", pad=14, loc='left', fontweight='bold')
    ax.set_xlabel("ვალის ჯამი (₾)", fontproperties=font_prop, fontsize=9, color="#7F8C8D")

    if font_prop:
        for label in ax.get_yticklabels():
            label.set_fontproperties(font_prop)
            label.set_fontsize(9)
            label.set_color("#2C3E50")

    for spine_name in ['top', 'right', 'left']:
        ax.spines[spine_name].set_visible(False)
    ax.spines['bottom'].set_color("#D5D8DC")
    ax.tick_params(axis='x', colors='#95A5A6', labelsize=8)
    ax.tick_params(axis='y', length=0)
    ax.xaxis.grid(True, color="#ECF0F1", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    if max_val > 0:
        ax.set_xlim(0, max_val * 1.18)

    for bar, val in zip(bars, top['ვალი']):
        ax.text(bar.get_width() + max_val * 0.015, bar.get_y() + bar.get_height() / 2,
                 f"{val:,.0f} ₾", va='center', ha='left', fontsize=8,
                 color="#2C3E50", fontproperties=font_prop)

    plt.tight_layout()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    plt.savefig(tmp.name, dpi=200, bbox_inches='tight', transparent=True)
    plt.close(fig)
    return tmp.name


class ExecutivePDF(FPDF):
    """FPDF subclass with a consistent header/footer chrome across all pages."""

    bold_available = False
    report_title = "ვალები–ავანსები — საერთო ანგარიში"

    def set_fonts(self):
        try:
            self.add_font('DejaVu', '', FONT_REGULAR_PATH)
            for cand in FONT_BOLD_CANDIDATES:
                if os.path.exists(cand):
                    self.add_font('DejaVu', 'B', cand)
                    ExecutivePDF.bold_available = True
                    break
            self.set_font('DejaVu', size=10)
        except Exception:
            self.set_font('Helvetica', size=10)

    def bold(self, size):
        style = 'B' if ExecutivePDF.bold_available else ''
        try:
            self.set_font('DejaVu', style, size)
        except Exception:
            self.set_font('Helvetica', style, size)

    def regular(self, size):
        try:
            self.set_font('DejaVu', '', size)
        except Exception:
            self.set_font('Helvetica', '', size)

    def header(self):
        if self.page_no() == 1:
            return  # cover/summary page draws its own hero header
        self.set_fill_color(*COLOR_HEADER_BG)
        self.rect(0, 0, self.w, 14, style='F')
        self.set_xy(10, 3.5)
        self.set_text_color(*COLOR_WHITE)
        self.bold(11)
        self.cell(0, 7, self.report_title, align='L')
        self.set_y(18)
        self.set_text_color(*COLOR_PRIMARY)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*COLOR_BORDER)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.set_y(-10)
        self.regular(8)
        self.set_text_color(*COLOR_MUTED)
        self.cell(0, 8, f"გვერდი {self.page_no()} / {{nb}}", align='C')


def draw_metric_card(pdf, x, y, w, h, label, value, accent_color, value_color):
    pdf.set_fill_color(*COLOR_LIGHT_BG)
    pdf.rect(x, y, w, h, style='F')
    pdf.set_fill_color(*accent_color)
    pdf.rect(x, y, 1.6, h, style='F')
    pdf.set_draw_color(*COLOR_BORDER)
    pdf.rect(x, y, w, h, style='D')

    pdf.set_xy(x + 6, y + 5)
    pdf.regular(8.5)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.cell(w - 10, 5, label)

    pdf.set_xy(x + 6, y + 12)
    pdf.bold(15)
    pdf.set_text_color(*value_color)
    pdf.cell(w - 10, 8, value)
    pdf.set_text_color(*COLOR_PRIMARY)


def table_header_row(pdf, cols, fill_color=COLOR_HEADER_BG, text_color=COLOR_WHITE, row_h=8):
    pdf.set_fill_color(*fill_color)
    pdf.set_text_color(*text_color)
    pdf.bold(9)
    for w, label, align in cols:
        pdf.cell(w, row_h, label, border=0, align=align, fill=True)
    pdf.ln(row_h)
    pdf.set_text_color(*COLOR_PRIMARY)


# --- PDF GENERATOR -------------------------------------------------------------------

def generate_pdf(df):
    pdf = ExecutivePDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.alias_nb_pages()
    pdf.set_fonts()

    # ---- Aggregate data (logic unchanged, presentation only) ----
    summary_data = []
    for proj in df['პროექტის დასახელება'].unique():
        sub = df[df['პროექტის დასახელება'] == proj]
        p_debt = sub['ვალები'].sum()
        p_adv = sub['ავანსები'].sum()
        summary_data.append({'პროექტი': proj, 'ვალი': p_debt, 'ავანსი': p_adv})

    sum_df = pd.DataFrame(summary_data)
    total_debts = sum_df['ვალი'].sum()
    total_advances = abs(sum_df['ავანსი'].sum())
    net_balance = total_debts - total_advances

    # =========================== PAGE 1 — EXECUTIVE SUMMARY ===========================
    pdf.add_page()

    # Hero header band
    pdf.set_fill_color(*COLOR_HEADER_BG)
    pdf.rect(0, 0, pdf.w, 34, style='F')
    pdf.set_xy(12, 8)
    pdf.set_text_color(*COLOR_WHITE)
    pdf.bold(19)
    pdf.cell(0, 10, "ვალები — ავანსები", align='L')
    pdf.set_xy(12, 20)
    pdf.regular(10.5)
    pdf.cell(0, 6, "Executive Summary  ·  By Account", align='L')
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.set_y(42)

    # Metric cards
    card_w = (pdf.w - 20 - 2 * 4) / 3
    card_h = 24
    card_y = pdf.get_y()
    draw_metric_card(pdf, 10, card_y, card_w, card_h,
                      "საერთო ვალები", f"{total_debts:,.2f} ₾", COLOR_DEBT, COLOR_DEBT)
    draw_metric_card(pdf, 10 + card_w + 4, card_y, card_w, card_h,
                      "საერთო ავანსები", f"({total_advances:,.2f}) ₾", COLOR_ADVANCE, COLOR_ADVANCE)
    draw_metric_card(pdf, 10 + 2 * (card_w + 4), card_y, card_w, card_h,
                      "სალდო (ვალი − ავანსი)", f"{net_balance:,.2f} ₾", COLOR_PRIMARY, COLOR_PRIMARY)
    pdf.set_y(card_y + card_h + 10)

    # Chart
    if len(sum_df) > 0 and total_debts > 0:
        try:
            chart_path = generate_debt_chart(sum_df)
            chart_w = pdf.w - 20
            chart_h = chart_w * (3.4 / 7.6)
            pdf.image(chart_path, x=10, y=pdf.get_y(), w=chart_w, h=chart_h)
            pdf.set_y(pdf.get_y() + chart_h + 8)
            try:
                os.remove(chart_path)
            except OSError:
                pass
        except Exception:
            pass  # never let chart rendering break the report

    # Per-project summary table
    pdf.bold(12)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.cell(0, 8, "პროექტების მიხედვით ჯამები", ln=True)
    pdf.ln(1)

    table_w = pdf.w - 20
    col_proj_w, col_debt_w, col_adv_w = table_w * 0.46, table_w * 0.27, table_w * 0.27
    table_header_row(pdf, [
        (col_proj_w, "პროექტის დასახელება", 'L'),
        (col_debt_w, "ვალი", 'R'),
        (col_adv_w, "ავანსი", 'R'),
    ], row_h=9)

    pdf.regular(9.5)
    for i, row in sum_df.iterrows():
        fill = COLOR_ZEBRA if i % 2 == 1 else COLOR_WHITE
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.cell(col_proj_w, 8, ("  " + str(row['პროექტი']))[:42], border='B', align='L', fill=True)
        pdf.set_text_color(*COLOR_DEBT)
        pdf.cell(col_debt_w, 8, f"{row['ვალი']:,.2f}  ", border='B', align='R', fill=True)
        pdf.set_text_color(*COLOR_ADVANCE)
        pdf.cell(col_adv_w, 8, f"({row['ავანსი']:,.2f})  ", border='B', align='R', fill=True)
        pdf.set_text_color(*COLOR_PRIMARY)
        pdf.ln(8)

    # ====================== DETAIL PAGES — ONE BLOCK PER PROJECT ======================
    for proj in df['პროექტის დასახელება'].unique():
        pdf.add_page()
        pdf.bold(14)
        pdf.set_text_color(*COLOR_PRIMARY)
        pdf.cell(0, 9, f"პროექტი: {proj}", ln=True)
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.line(10, pdf.get_y(), pdf.w - 10, pdf.get_y())
        pdf.ln(4)

        proj_df = df[df['პროექტის დასახელება'] == proj]

        # --- Debtors block ---
        debtors = proj_df[proj_df['ვალები'] > 0]
        if not debtors.empty:
            pdf.bold(11)
            pdf.set_text_color(*COLOR_DEBT)
            pdf.cell(0, 7, "მევალეების სია", ln=True)
            pdf.set_text_color(*COLOR_PRIMARY)
            pdf.ln(1)

            cols = [(50, "სახელი გვარი", 'L'), (28, "პირადი №", 'C'),
                    (24, "ვალი", 'R'), (32, "ტელეფონი", 'C'), (56, "შენიშვნა", 'L')]
            table_header_row(pdf, cols, fill_color=COLOR_DEBT, row_h=8)

            pdf.regular(8.5)
            for i, (_, r) in enumerate(debtors.iterrows()):
                fill = COLOR_DEBT_LIGHT if i % 2 == 1 else COLOR_WHITE
                pdf.set_fill_color(*fill)
                pdf.set_draw_color(*COLOR_BORDER)
                pdf.cell(50, 7.5, ("  " + str(r['სახელი გვარი']))[:32], border='B', fill=True)
                pdf.cell(28, 7.5, str(r['პირადი ნომერი']), border='B', align='C', fill=True)
                pdf.set_text_color(*COLOR_DEBT)
                pdf.cell(24, 7.5, f"{r['ვალები']:.2f}", border='B', align='R', fill=True)
                pdf.set_text_color(*COLOR_PRIMARY)
                pdf.cell(32, 7.5, str(r['ტელეფონი'])[:14], border='B', align='C', fill=True)
                pdf.cell(56, 7.5, ("  " + str(r['შენიშვნა']))[:30], border='B', fill=True)
                pdf.ln(7.5)

            pdf.ln(2)
            pdf.bold(9.5)
            pdf.set_text_color(*COLOR_DEBT)
            pdf.cell(0, 7, f"ამ პროექტის ჯამური ვალი: {debtors['ვალები'].sum():,.2f} ₾", ln=True)
            pdf.set_text_color(*COLOR_PRIMARY)
            pdf.ln(4)

        # --- Advances block ---
        advances = proj_df[proj_df['ავანსები'] > 0]
        if not advances.empty:
            pdf.bold(11)
            pdf.set_text_color(*COLOR_ADVANCE)
            pdf.cell(0, 7, "ავანსების სია", ln=True)
            pdf.set_text_color(*COLOR_PRIMARY)
            pdf.ln(1)

            cols = [(80, "სახელი გვარი", 'L'), (50, "პირადი №", 'C'), (60, "ავანსი", 'R')]
            table_header_row(pdf, cols, fill_color=COLOR_ADVANCE, row_h=8)

            pdf.regular(8.5)
            for i, (_, r) in enumerate(advances.iterrows()):
                fill = COLOR_ADVANCE_LIGHT if i % 2 == 1 else COLOR_WHITE
                pdf.set_fill_color(*fill)
                pdf.set_draw_color(*COLOR_BORDER)
                pdf.cell(80, 7.5, ("  " + str(r['სახელი გვარი']))[:48], border='B', fill=True)
                pdf.cell(50, 7.5, str(r['პირადი ნომერი']), border='B', align='C', fill=True)
                pdf.set_text_color(*COLOR_ADVANCE)
                pdf.cell(60, 7.5, f"({r['ავანსები']:.2f})  ", border='B', align='R', fill=True)
                pdf.set_text_color(*COLOR_PRIMARY)
                pdf.ln(7.5)

            pdf.ln(2)
            pdf.bold(9.5)
            pdf.set_text_color(*COLOR_ADVANCE)
            pdf.cell(0, 7, f"ამ პროექტის ჯამური ავანსი: ({advances['ავანსები'].sum():,.2f}) ₾", ln=True)
            pdf.set_text_color(*COLOR_PRIMARY)

    return pdf.output()


# =====================================================================================
#  STREAMLIT UI
# =====================================================================================

st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: #F8F9FA;
        border: 1px solid #E5E7EA;
        border-radius: 10px;
        padding: 14px 16px;
    }
    div[data-testid="stMetricLabel"] { color: #7F8C8D; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 Accounting Tool — By A/C")
st.caption("ვალები / ავანსები — დამუშავება, შესწორება ტელეფონის ნომრებით და PDF ანგარიში")

st.markdown("---")
up_col1, up_col2 = st.columns(2)
with up_col1:
    f1 = st.file_uploader("📁 ატვირთეთ prnValiSagad1.csv", type=['csv'])
with up_col2:
    f2 = st.file_uploader("📁 ატვირთეთ valebi.csv", type=['csv'])

if f1 and f2:
    df1 = pd.read_csv(f1)
    df2 = pd.read_csv(f2)

    for col in ['ვალები', 'ავანსები']:
        df1[col] = df1[col].apply(safe_float)
        
    # აქცევს ყველა ავანსს დადებით რიცხვად, რათა PDF-ის ფილტრებმა (ავანსები > 0) სწორად იპოვონ ისინი
    df1['ავანსები'] = df1['ავანსები'].abs()

    with st.spinner('მუშავდება...'):
        df1[['ტელეფონი', 'შენიშვნა']] = df1.apply(lambda row: pd.Series(match_phone(row, df2)), axis=1)

    # ----------------------------- DASHBOARD -----------------------------
    st.markdown("---")
    st.subheader("📈 ფინანსური მიმოხილვა")

    total_debt = df1['ვალები'].sum()
    # abs() უზრუნველყოფს, რომ ავანსი ყოველთვის დადებითი იყოს და ნიშნები არ აირიოს
    total_advance = abs(df1['ავანსები'].sum())
    net_balance = total_debt - total_advance
    debtor_rows = df1[df1['ვალები'] > 0]
    not_found = (debtor_rows['ტელეფონი'] == "ნომერი ვერ მოიძებნა").sum()
    duplicates = (debtor_rows['ტელეფონი'] == "დუბლიკატია").sum()
    matched = max(len(debtor_rows) - not_found - duplicates, 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 საერთო ვალები", f"{total_debt:,.2f} ₾")
    m2.metric("💵 საერთო ავანსები", f"{total_advance:,.2f} ₾")
    m3.metric("⚖️ სალდო", f"{net_balance:,.2f} ₾")
    m4.metric("📞 დადასტურებული ნომრები", f"{matched} / {len(debtor_rows)}")

    st.markdown("##### 🔎 მონაცემთა შესწორების სტატუსი")
    s1, s2, s3 = st.columns(3)
    with s1:
        if not_found > 0:
            st.error(f"❌ ვერ მოიძებნა ნომერი: {not_found} ჩანაწერი")
        else:
            st.success("✅ ყველა ნომერი მოიძებნა")
    with s2:
        if duplicates > 0:
            st.warning(f"⚠️ დუბლირებული ჩანაწერები: {duplicates}")
        else:
            st.success("✅ დუბლიკატები არ მოიძებნა")
    with s3:
        st.info(f"📁 პროექტების რაოდენობა: {df1['პროექტის დასახელება'].nunique()}")

    # ----------------------------- PREVIEW -----------------------------
    st.markdown("---")
    st.subheader("📋 მონაცემების პრევიუ")

    def style_preview(d):
        def color_debt(val):
            try:
                return 'color: #C0392B; font-weight:600;' if float(val) > 0 else ''
            except Exception:
                return ''

        def color_adv(val):
            try:
                return 'color: #277455; font-weight:600;' if float(val) > 0 else ''
            except Exception:
                return ''

        return (
        d.style
        .map(color_debt, subset=['ვალები'])
        .map(color_adv, subset=['ავანსები'])
        .format({'ვალები': '{:,.2f}', 'ავანსები': '{:,.2f}'})
    )
        

    for p in df1['პროექტის დასახელება'].unique():
        p_df = df1[df1['პროექტის დასახელება'] == p]
        p_debt = p_df['ვალები'].sum()
        p_adv = p_df['ავანსები'].sum()
        with st.expander(f"📁 {p}   —   ვალი: {p_debt:,.2f} ₾   |   ავანსი: ({p_adv:,.2f}) ₾"):
            st.dataframe(
                style_preview(p_df[['სახელი გვარი', 'პირადი ნომერი', 'ვალები', 'ავანსები', 'ტელეფონი', 'შენიშვნა']]),
                use_container_width=True,
                hide_index=True,
            )

    # ----------------------------- PDF EXPORT -----------------------------
    st.markdown("---")
    st.subheader("🚀 ანგარიშის გენერირება")
    if st.button("🚀 PDF დოკუმენტის გენერირება", type="primary"):
        with st.spinner("PDF გენერირდება..."):
            pdf_bytes = generate_pdf(df1)
        st.success("✅ PDF მზად არის!")
        st.download_button(
            "📥 გადმოწერეთ PDF",
            data=bytes(pdf_bytes),
            file_name="Report_AC.pdf",
            mime="application/pdf",
            type="primary",
        )
else:
    st.info("⬆️ გთხოვთ ატვირთოთ ორივე CSV ფაილი დასაწყებად.")
