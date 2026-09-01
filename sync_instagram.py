import os
import sys
import glob
import json
import subprocess
import time
import re
import urllib.request
from playwright.sync_api import sync_playwright

def cleanup_old_media(allowed_files):
    """Remove mídias antigas que não estão na lista dos posts ativos"""
    for file_path in glob.glob("media_*.*") + glob.glob("video_*.mp4"):
        if file_path not in allowed_files:
            try:
                os.remove(file_path)
                print(f"🗑️ Mídia antiga removida: {file_path}")
            except Exception as e:
                print(f"Erro ao remover {file_path}: {e}")

def extract_caption_from_meta(meta_text):
    """Extrai o texto limpo da legenda a partir das meta tags"""
    if not meta_text:
        return ""
    match = re.search(r'["“](.+?)["”]', meta_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return meta_text.strip()

def fetch_post_urls(page, browser, username, target_count=12):
    posts_urls = []
    routes = [
        f"https://www.instagram.com/{username}/reels/",
        f"https://www.instagram.com/{username}/"
    ]

    for route in routes:
        print(f"🌐 Tentando acessar: {route}")
        try:
            page.goto(route, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
        except Exception as e:
            print(f"Aviso ao carregar rota {route}: {e}")
            continue

        # 1. Detecção de bloqueio de sessão / tela de login 🔐
        current_url = page.url
        login_detected = (
            "/accounts/login/" in current_url
            or page.query_selector("input[name='username']") is not None
        )

        if login_detected:
            print("🛑 ERRO CRÍTICO: Sessão expirada ou bloqueada pelo Instagram!")
            print("👉 Renove o secret INSTAGRAM_COOKIES no repositório.")
            browser.close()
            sys.exit(1)

        # 2. Varredura ordenada por posição visual 📜
        for _ in range(6):
            raw_items = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll("a[href*='/reel/'], a[href*='/p/']"));
                return links.map(el => {
                    const rect = el.getBoundingClientRect();
                    const isPinned = !!el.querySelector("svg[aria-label*='Pin'], svg[aria-label*='Fixado'], svg[title*='Pin'], svg[title*='Fixado']");
                    return {
                        href: el.getAttribute('href'),
                        top: Math.round(rect.top + window.scrollY),
                        left: Math.round(rect.left),
                        isPinned: isPinned
                    };
                });
            }""")

            raw_items.sort(key=lambda item: (item['top'], item['left']))

            for item in raw_items:
                if item.get("isPinned"):
                    continue
                href = item.get("href")
                if href:
                    full_url = f"https://www.instagram.com{href}" if href.startswith("/") else href
                    clean_url = full_url.split("?")[0]
                    if clean_url not in posts_urls:
                        posts_urls.append(clean_url)

            if len(posts_urls) >= target_count:
                break

            page.mouse.wheel(0, 800)
            time.sleep(2)

        if posts_urls:
            print(f"✅ Encontrados {len(posts_urls)} posts na rota {route}")
            break

    return posts_urls[:target_count]

def main():
    cookies_raw = os.environ.get("INSTAGRAM_COOKIES", "")
    cookie_file = "cookies.txt"
    with open(cookie_file, "w", encoding="utf-8") as f:
        f.write(cookies_raw)

    playwright_cookies = []
    for line in cookies_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain, _, path, secure, expires, name, value = parts[:7]
            playwright_cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": secure.lower() == "true",
                "expires": float(expires) if expires.isdigit() else -1
            })

    username = "studiofit.gb"
    target_count = 12

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        if playwright_cookies:
            context.add_cookies(playwright_cookies)

        page = context.new_page()
        
        posts_urls = fetch_post_urls(page, browser, username, target_count)
        print(f"\nTotal de posts coletados: {len(posts_urls)}")

        if not posts_urls:
            print("❌ Nenhum post localizado para processamento.")
            browser.close()
            return

        posts_data = []
        allowed_files = []

        for idx, post_url in enumerate(posts_urls, start=1):
            print(f"\n--- Processando Post #{idx}: {post_url} ---")
            is_video = "/reel/" in post_url
            caption = ""
            image_download_url = ""

            try:
                page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                meta_data = page.evaluate("""() => {
                    const ogDesc = document.querySelector("meta[property='og:description']")?.getAttribute('content') || "";
                    const desc = document.querySelector("meta[name='description']")?.getAttribute('content') || "";
                    const ogTitle = document.querySelector("meta[property='og:title']")?.getAttribute('content') || "";
                    const h1 = document.querySelector("h1")?.innerText || "";
                    const spanText = document.querySelector("article span[dir='auto'], div[class*='_a9zs'] span")?.innerText || "";
                    return { ogDesc, desc, ogTitle, h1, spanText };
                }""")

                raw_meta = meta_data.get('ogDesc') or meta_data.get('desc') or meta_data.get('ogTitle') or ""
                extracted = extract_caption_from_meta(raw_meta)

                if extracted and len(extracted) > 3:
                    caption = extracted
                elif meta_data.get('h1'):
                    caption = meta_data['h1'].strip()
                elif meta_data.get('spanText'):
                    caption = meta_data['spanText'].strip()

                video_elem = page.query_selector("video")
                if video_elem:
                    is_video = True
                elif not is_video:
                    img_elem = page.query_selector("article img, div[role='dialog'] img, img[style*='object-fit']")
                    if img_elem:
                        image_download_url = img_elem.get_attribute("src") or ""

            except Exception as e:
                print(f"Aviso ao extrair dados do post #{idx}: {e}")

            if is_video:
                output_filename = f"media_{idx}.mp4"
                temp_raw = f"temp_raw_{idx}.mp4"
                allowed_files.append(output_filename)

                cmd_download = [
                    "yt-dlp",
                    "--cookies", cookie_file,
                    "--no-check-certificates",
                    "-f", "bestvideo+bestaudio/best",
                    "-o", temp_raw,
                    "--force-overwrites",
                    post_url
                ]
                subprocess.run(cmd_download, capture_output=True, text=True)

                if os.path.exists(temp_raw):
                    cmd_ffmpeg = [
                        "ffmpeg", "-y",
                        "-i", temp_raw,
                        "-vf", "scale='min(720,iw)':-2",
                        "-c:v", "libx264",
                        "-crf", "26",
                        "-preset", "veryfast",
                        "-c:a", "aac",
                        "-b:a", "96k",
                        "-movflags", "+faststart",
                        output_filename
                    ]
                    subprocess.run(cmd_ffmpeg, capture_output=True, text=True)
                    try:
                        os.remove(temp_raw)
                    except Exception:
                        pass

                posts_data.append({
                    "id": idx,
                    "type": "video",
                    "url": post_url,
                    "media_file": output_filename,
                    "caption": caption if caption else "Studio Fit GB - Treinamento personalizado e saúde em foco.",
                    "updated_at": time.strftime("%d/%m/%Y às %H:%M")
                })

            else:
                output_filename = f"media_{idx}.jpg"
                allowed_files.append(output_filename)

                downloaded = False
                if image_download_url:
                    try:
                        req = urllib.request.Request(image_download_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=20) as response, open(output_filename, 'wb') as out_file:
                            out_file.write(response.read())
                        downloaded = True
                    except Exception as e:
                        print(f"Erro ao baixar imagem: {e}")

                if not downloaded:
                    try:
                        img_node = page.query_selector("article img, img[style*='object-fit']")
                        if img_node:
                            img_node.screenshot(path=output_filename)
                            downloaded = True
                    except Exception as e:
                        print(f"Erro ao salvar screenshot: {e}")

                posts_data.append({
                    "id": idx,
                    "type": "image",
                    "url": post_url,
                    "media_file": output_filename,
                    "caption": caption if caption else "Studio Fit GB - Supere seus limites todos os dias.",
                    "updated_at": time.strftime("%d/%m/%Y às %H:%M")
                })

        browser.close()

    cleanup_old_media(allowed_files)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(posts_data, f, ensure_ascii=False, indent=2)

    if os.path.exists(cookie_file):
        os.remove(cookie_file)

    print("\n✅ Concluído! Posts sincronizados e organizados com sucesso.")

if __name__ == "__main__":
    main()
