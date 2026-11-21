"""체험 계정 합성 서류 만들기(T12). 결과 파일은 `app/samples/`에 커밋한다.

    uv run python -m scripts.make_samples [--font 글꼴.ttf] [--out app/samples]

- 모든 이름·번호·기관은 지어낸 값이고, 서류마다 "합성 데이터" 띠와 메타데이터를 넣는다.
  실제 은행·국세청·메신저의 로고·직인·색은 흉내 내지 않는다.
- 거래 행과 인용 문구·줄 번호는 가짜 분석기(`app/agent/scripted.py`)의 값을 그대로 쓴다.
  거래 행을 더 넣지 않는다(실제 분석과 가짜 분석의 거래 목록이 같게, T12 결정 ③).
- 글꼴: Noto Sans KR(SIL Open Font License 1.1). 글꼴 파일은 레포에 두지 않는다.
  PDF에는 쓴 글자만 들어가고(OFL 허용), PNG는 그림이라 글꼴 파일이 아니다.
- 같은 글꼴로 다시 돌리면 같은 파일이 나온다(PDF `invariant`).
"""

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.agent.scripted import (
    GOODS_CHAT_QUOTE,
    GOODS_CHAT_REGION,
    GOODS_ROWS,
    THREAT_QUOTE,
    THREAT_REGION,
    UNEXPECTED_ROWS,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FONT = Path("C:/Windows/Fonts/NotoSansKR-VF.ttf")
SYNTHETIC = "합성 데이터 · 시연용 · 실제 인물·기관과 무관"
SYNTHETIC_NOTE = "Proofy 시연을 위해 만든 합성 데이터입니다. 실제 인물·기관·거래가 아닙니다."
BANNER = "#B42318"

# 가짜 분석기의 가린 이름(`김*수`) ↔ 서류에 적힌 가상 이름. 가리는 일은 마스킹(T14)이 한다
FULL_NAMES = {"박*진": "박서진", "김*수": "김민수", "이*호": "이준호"}
CARD = "체크카드 결제"


# ---------------------------------------------------------------- 거래내역서(텍스트 PDF)


@dataclass(frozen=True)
class Statement:
    holder: str
    account: str
    opening_balance: int
    rows: tuple  # GOODS_ROWS 모양
    times: dict[str, str]  # 행 key → 시각


GOODS_STATEMENT = Statement(
    holder="정하늘",
    account="999-0000-1234-56",
    opening_balance=118_500,
    rows=GOODS_ROWS,
    times={"t1": "10:41", "t2": "14:22", "t3": "19:05"},
)
UNEXPECTED_STATEMENT = Statement(
    holder="한도윤",
    account="999-0000-5678-90",
    opening_balance=61_200,
    rows=UNEXPECTED_ROWS,
    times={"t1": "12:37", "t2": "21:48"},
)
PERIOD = (date(2026, 11, 1), date(2026, 11, 14))


def statement_lines(st: Statement) -> list[tuple[str, str, str, str, str]]:
    """표의 행(거래일시, 구분, 거래금액, 거래후잔액, 거래상대·적요)."""
    balance = st.opening_balance
    lines = []
    for key, day, direction, amount, who in st.rows:
        balance += amount if direction == "IN" else -amount
        lines.append(
            (
                f"{day.isoformat()} {st.times[key]}",
                "입금" if direction == "IN" else "출금",
                f"{amount:,}",
                f"{balance:,}",
                FULL_NAMES[who] if who else CARD,
            )
        )
    return lines


def draw_cells(c: canvas.Canvas, y: float, cells: list[tuple[float, str, str]]) -> None:
    """한 줄을 텍스트 객체 하나로 쓴다. 칸마다 따로 쓰면 `pypdf`가 칸마다 줄을 바꿔서,
    거래 한 행의 날짜·금액이 한 줄(영역)에 있어야 하는 행 추출(T15)이 어려워진다.
    cells = (x, 글, "L" 왼쪽 정렬 | "R" 오른쪽 정렬)
    """
    font, size = c._fontname, c._fontsize
    t = c.beginText(0, y)
    cursor = 0.0
    for x, text, align in cells:
        start = x - pdfmetrics.stringWidth(text, font, size) if align == "R" else x
        t.moveCursor(start - cursor, 0)
        t.textOut(text)
        cursor = start
    c.drawText(t)


def make_statement_pdf(path: Path, st: Statement) -> None:
    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle("거래내역 조회 (합성 데이터)")
    c.setAuthor("Proofy 합성 데이터")
    c.setSubject(SYNTHETIC_NOTE)

    c.setFillColor(HexColor(BANNER))
    c.rect(0, height - 34, width, 34, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("NotoSansKR", 11)
    c.drawCentredString(width / 2, height - 22, SYNTHETIC)

    c.setFillColor(HexColor("#111111"))
    c.setFont("NotoSansKR", 18)
    c.drawString(48, height - 80, "거래내역 조회")
    c.setFont("NotoSansKR", 10.5)
    info = [
        ("은행", "샘플은행(가상)"),
        ("예금주", st.holder),
        ("계좌번호", st.account),
        ("조회기간", f"{PERIOD[0].isoformat()} ~ {PERIOD[1].isoformat()}"),
    ]
    y = height - 110
    for label, value in info:
        draw_cells(c, y, [(48, label, "L"), (120, value, "L")])
        y -= 18

    # 열 x 위치. 금액은 오른쪽 정렬
    cols = [(48, "L"), (170, "L"), (300, "R"), (380, "R"), (410, "L")]
    header = ("거래일시", "구분", "거래금액", "거래후잔액", "거래상대·적요")
    y -= 14
    c.setFillColor(HexColor("#F2F4F7"))
    c.rect(40, y - 7, width - 80, 24, stroke=0, fill=1)
    c.setFillColor(HexColor("#111111"))
    draw_cells(c, y, [(x, text, align) for (x, align), text in zip(cols, header, strict=True)])
    c.setStrokeColor(HexColor("#D0D5DD"))
    for row in statement_lines(st):
        y -= 26
        c.line(40, y + 17, width - 40, y + 17)
        draw_cells(c, y, [(x, text, align) for (x, align), text in zip(cols, row, strict=True)])
    c.line(40, y - 9, width - 40, y - 9)

    c.setFont("NotoSansKR", 9)
    c.setFillColor(HexColor("#667085"))
    c.drawString(48, y - 30, f"조회기간 내 거래 {len(st.rows)}건")
    c.drawString(48, 40, SYNTHETIC_NOTE)
    c.showPage()
    c.save()


# ---------------------------------------------------------------- PNG 공통


class Fonts:
    def __init__(self, path: Path):
        self.path = path

    def get(self, size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
        font = ImageFont.truetype(str(self.path), size)
        font.set_variation_by_name(weight)
        return font


def text_size(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text)
    return right - left, bottom - top


def png_info(title: str) -> PngInfo:
    info = PngInfo()
    info.add_itxt("Title", title)
    info.add_itxt("Description", SYNTHETIC_NOTE)
    return info


def draw_banner(d: ImageDraw.ImageDraw, width: int, fonts: Fonts, height: int = 56) -> int:
    d.rectangle((0, 0, width, height), fill=BANNER)
    font = fonts.get(24, "Medium")
    w, h = text_size(font, SYNTHETIC)
    d.text(((width - w) / 2, (height - h) / 2), SYNTHETIC, font=font, fill="white", anchor="lt")
    return height


# ---------------------------------------------------------------- 대화 화면(PNG)

GOODS_CHAT_TITLE = "김민수 (거래처)"
THREAT_TITLE = "010-0000-4821"

# 말풍선 하나 = 한 줄. ("in" 받은 말, "out" 보낸 말, "date" 날짜 구분선)
GOODS_CHAT: tuple[tuple[str, str], ...] = (
    ("date", "2026년 11월 6일 금요일"),
    ("in", "안녕하세요, 하늘가죽공방 맞죠?"),
    ("out", "네 안녕하세요!"),
    ("in", "온라인 쇼핑몰 보고 연락드렸어요"),
    ("in", "가죽 지갑을 매장에 놓아 보려고요"),
    ("out", "감사합니다. 어떤 색상 찾으세요?"),
    ("in", "브라운으로 몇 개 되나요?"),
    ("out", "브라운은 지금 3개 있어요"),
    ("in", "가격은 얼마예요?"),
    ("out", "3개 다 하시면 조금 빼 드릴게요"),
    ("in", GOODS_CHAT_QUOTE),
    ("out", "네 그렇게 해 드릴게요"),
    ("date", "2026년 11월 7일 토요일"),
    ("in", "내일 입금할게요. 계좌 알려 주세요"),
    ("out", f"샘플은행 {GOODS_STATEMENT.account} {GOODS_STATEMENT.holder}입니다"),
)
THREAT_CHAT: tuple[tuple[str, str], ...] = (
    ("date", "2026년 11월 13일 금요일"),
    ("in", THREAT_QUOTE),
    ("in", "계좌 막혀서 곤란하지?"),
    ("in", "오늘 안에 답 없으면 그냥 둔다"),
)


def chat_lines(title: str, messages: tuple[tuple[str, str], ...]) -> list[str]:
    """화면 위에서부터 읽히는 줄(띠, 제목, 메시지). 인용 줄 번호 확인용."""
    return [SYNTHETIC, title, *(text for _, text in messages)]


def make_chat_png(
    path: Path,
    fonts: Fonts,
    title: str,
    messages: tuple[tuple[str, str], ...],
    out_color: str = "#D6E8FF",
) -> None:
    width = 720
    body = fonts.get(28, "Medium")
    small = fonts.get(22, "Regular")
    pad_x, pad_y, gap = 20, 14, 18

    # 높이 먼저 계산
    _, line_h = text_size(body, "가나다 123")
    content = 0
    for kind, _ in messages:
        content += (44 if kind == "date" else line_h + pad_y * 2) + gap
    height = max(1280, 56 + 90 + 30 + content + 60)

    img = Image.new("RGB", (width, height), "#EEF1F5")
    d = ImageDraw.Draw(img)
    y = draw_banner(d, width, fonts)

    # 제목 한 줄만(줄이 늘면 인용 줄 번호가 밀린다)
    d.rectangle((0, y, width, y + 90), fill="#FFFFFF")
    d.line((0, y + 90, width, y + 90), fill="#D0D5DD", width=2)
    d.text((32, y + 26), title, font=fonts.get(32, "Bold"), fill="#111111")
    y += 90 + 30

    for kind, text in messages:
        if kind == "date":
            w, h = text_size(small, text)
            x = (width - w) / 2
            d.rounded_rectangle((x - 18, y, x + w + 18, y + 40), radius=20, fill="#D0D5DD")
            d.text((x, y + (40 - h) / 2), text, font=small, fill="#344054", anchor="lt")
            y += 44 + gap
            continue
        w, _ = text_size(body, text)
        bw, bh = w + pad_x * 2, line_h + pad_y * 2
        x = 28 if kind == "in" else width - 28 - bw
        fill = "#FFFFFF" if kind == "in" else out_color
        d.rounded_rectangle((x, y, x + bw, y + bh), radius=18, fill=fill, outline="#C9CED6")
        d.text((x + pad_x, y + pad_y), text, font=body, fill="#111111", anchor="lt")
        y += bh + gap

    d.text((28, height - 44), SYNTHETIC_NOTE, font=fonts.get(18), fill="#667085")
    img.save(path, pnginfo=png_info(title), optimize=True)


# ---------------------------------------------------------------- 사업자등록증명(PNG)

BUSINESS_FIELDS: tuple[tuple[str, str], ...] = (
    ("등록번호", "123-45-67890"),
    ("상호", "하늘가죽공방"),
    ("대표자", GOODS_STATEMENT.holder),
    ("개업일", "2025년 3월 2일"),
    ("사업장 소재지", "서울특별시 가상구 샘플로 12, 3층"),
    ("업태", "소매업"),
    ("종목", "전자상거래 소매업"),
)


def make_business_reg_png(path: Path, fonts: Fonts) -> None:
    width, height = 1240, 1754
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    top = draw_banner(d, width, fonts, height=70)

    title_font = fonts.get(60, "Bold")
    title = "사업자등록증명"
    w, _ = text_size(title_font, title)
    d.text(((width - w) / 2, top + 120), title, font=title_font, fill="#111111")
    sub = fonts.get(28)
    w, _ = text_size(sub, "(합성 샘플)")
    d.text(((width - w) / 2, top + 210), "(합성 샘플)", font=sub, fill="#667085")

    label_font, value_font = fonts.get(32, "Medium"), fonts.get(32)
    x0, x1, x2 = 120, 420, width - 120
    y = top + 320
    row_h = 92
    d.line((x0, y, x2, y), fill="#344054", width=3)
    for label, value in BUSINESS_FIELDS:
        d.rectangle((x0, y, x1, y + row_h), fill="#F2F4F7")
        d.text((x0 + 30, y + 26), label, font=label_font, fill="#111111")
        d.text((x1 + 30, y + 26), value, font=value_font, fill="#111111")
        y += row_h
        d.line((x0, y, x2, y), fill="#98A2B3", width=2)
    d.line((x0, top + 320, x0, y), fill="#98A2B3", width=2)
    d.line((x1, top + 320, x1, y), fill="#98A2B3", width=2)
    d.line((x2, top + 320, x2, y), fill="#98A2B3", width=2)

    body = fonts.get(30)
    closing = (
        "위 사업자의 등록 사실을 증명합니다(합성 샘플).",
        "발급일  2026년 11월 20일",
        "발급기관  (가상) 발급기관",
    )
    for i, line in enumerate(closing):
        d.text((x0, y + 90 + i * 66), line, font=body, fill="#111111")
    d.text((x0, height - 110), SYNTHETIC_NOTE, font=fonts.get(24), fill="#667085")
    img.save(path, pnginfo=png_info("사업자등록증명 (합성 데이터)"), optimize=True)


# ---------------------------------------------------------------- 실행


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT, help="Noto Sans KR 글꼴 파일")
    parser.add_argument("--out", type=Path, default=ROOT / "app" / "samples")
    args = parser.parse_args()

    # 가짜 분석기가 가리키는 줄 번호에 인용 문구가 있어야 한다
    assert chat_lines(GOODS_CHAT_TITLE, GOODS_CHAT)[GOODS_CHAT_REGION] == GOODS_CHAT_QUOTE
    assert chat_lines(THREAT_TITLE, THREAT_CHAT)[THREAT_REGION] == THREAT_QUOTE

    pdfmetrics.registerFont(TTFont("NotoSansKR", str(args.font)))
    fonts = Fonts(args.font)
    goods, unexpected = args.out / "goods", args.out / "unexpected"
    goods.mkdir(parents=True, exist_ok=True)
    unexpected.mkdir(parents=True, exist_ok=True)

    make_statement_pdf(goods / "transaction_record.pdf", GOODS_STATEMENT)
    make_chat_png(goods / "chat.png", fonts, GOODS_CHAT_TITLE, GOODS_CHAT)
    make_business_reg_png(goods / "business_reg.png", fonts)
    make_statement_pdf(unexpected / "transaction_record.pdf", UNEXPECTED_STATEMENT)
    make_chat_png(
        unexpected / "threat_message.png",
        fonts,
        THREAT_TITLE,
        THREAT_CHAT,
        out_color="#E4E7EC",
    )
    for p in sorted(args.out.rglob("*.*")):
        print(f"{p.relative_to(args.out)}  {p.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
