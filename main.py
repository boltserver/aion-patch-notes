import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
from bs4 import BeautifulSoup
import aiosqlite

# ================= 설정 =================
TOKEN = "MTQ1OTEzOTQ1MzY0MDc3MzY1Mg.G_92s0.NlSBulmal5RFdCTvLug-PViCk5bRL0QXCIMYIY"

NOTICE_URL = "https://aion2.plaync.com/ko-kr/board/notice/list"
UPDATE_URL = "https://aion2.plaync.com/ko-kr/board/update/list"
BASE_URL = "https://aion2.plaync.com"

KEYWORDS = [
    "점검", "시간", "일시", "기간",
    "업데이트", "패치", "변경", "수정", "개선",
    "서버", "장애", "오류", "안정화",
    "이벤트", "보상", "지급", "오픈", "종료"
]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DB =================
async def init_db():
    async with aiosqlite.connect("data.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            url TEXT PRIMARY KEY
        )
        """)
        await db.commit()

# ================= 크롤링 =================
async def fetch_list(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            html = await r.text()

    soup = BeautifulSoup(html, "html.parser")
    items = []

    for a in soup.select("a.link"):
        title = a.text.strip()
        link = BASE_URL + a["href"]
        items.append((title, link))

    return items[:5]

async def fetch_summary(detail_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(detail_url) as r:
            html = await r.text()

    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".board-view__content")

    if not content:
        return {"has_summary": False, "text": ""}

    text = content.get_text("\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    if not lines:
        return {"has_summary": False, "text": ""}

    first_line = lines[0]

    matched = [
        line for line in lines
        if any(keyword in line for keyword in KEYWORDS)
    ]

    if matched:
        summary = "\n".join(matched[:5])
        if len(summary) > 400:
            summary = summary[:400] + "..."
        return {"has_summary": True, "text": summary}

    return {"has_summary": False, "text": first_line}

# ================= Embed 전송 =================
async def send_embed(channel, title, link, summary_data, category):
    description = f"**{title}**\n\n{summary_data['text']}"

    embed = discord.Embed(
        title=f"[아이온2] {category}",
        description=description,
        color=0x3BA55D
    )

    embed.set_thumbnail(
        url="https://i.imgur.com/7ZQZQZq.png"
    )
    embed.set_image(
        url="https://i.imgur.com/Jh8KpGf.png"
    )

    embed.add_field(
        name="📌 원문",
        value=f"[공지 바로가기]({link})",
        inline=False
    )

    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="공지 열기",
            url=link,
            style=discord.ButtonStyle.link
        )
    )

    await channel.send(embed=embed, view=view)

# ================= 공지 체크 =================
@tasks.loop(minutes=10)
async def check_updates():
    targets = [
        (NOTICE_URL, "공지사항"),
        (UPDATE_URL, "업데이트")
    ]

    async with aiosqlite.connect("data.db") as db:
        for url, category in targets:
            posts = await fetch_list(url)

            for title, link in posts:
                cur = await db.execute(
                    "SELECT 1 FROM posts WHERE url=?",
                    (link,)
                )
                if await cur.fetchone():
                    continue

                summary = await fetch_summary(link)

                await db.execute(
                    "INSERT INTO posts VALUES (?)",
                    (link,)
                )
                await db.commit()

                cur = await db.execute(
                    "SELECT channel_id FROM channels"
                )
                for (channel_id,) in await cur.fetchall():
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await send_embed(
                            channel, title, link, summary, category
                        )

# ================= 슬래시 명령 =================
@bot.tree.command(name="채널설정", description="아이온2 공지를 받을 채널로 설정합니다")
async def set_channel(interaction: discord.Interaction):
    async with aiosqlite.connect("data.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO channels VALUES (?, ?)",
            (interaction.guild_id, interaction.channel_id)
        )
        await db.commit()

    await interaction.response.send_message(
        "✅ 이 채널로 아이온2 공지가 전송됩니다.",
        ephemeral=True
    )

@bot.tree.command(name="수동확인", description="아이온2 공지를 즉시 확인합니다")
async def manual_check(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🔍 공지 확인 중...",
        ephemeral=True
    )
    await check_updates()

# ================= 이벤트 =================
@bot.event
async def on_ready():
    await init_db()
    await bot.tree.sync()
    check_updates.start()

    await bot.change_presence(
        activity=discord.Game(
            name=f"{len(bot.guilds)}개 서버에서 아이온2 감시중"
        )
    )

    app_info = await bot.application_info()
    invite = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={app_info.id}"
        "&scope=bot%20applications.commands"
        "&permissions=3147776"
    )

    print("===================================")
    print("🤖 봇 실행 완료")
    print("봇 초대 링크:")
    print(invite)
    print("===================================")

bot.run(TOKEN)
