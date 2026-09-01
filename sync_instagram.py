def fetch_post_urls(page, username, target_count=12):
    posts_urls = []
    routes = [
        f"https://www.instagram.com/{username}/reels/",
        f"https://www.instagram.com/{username}/"
    ]

    for route in routes:
        print(f"🌐 Tentando acessar: {route}")
        page.goto(route, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        # 1. Detecção de bloqueio de sessão / tela de login 🔐
        current_url = page.url
        login_detected = (
            "/accounts/login/" in current_url
            or page.query_selector("input[name='username']") is not None
        )

        if login_detected:
            print("⚠️ AVISO: Sessão expirada ou bloqueada pelo Instagram!")
            print("👉 Renove o secret INSTAGRAM_COOKIES no repositório.")
            break

        # 2. Varredura com rolagem de tela 📜
        for _ in range(6):
            # Coleta os seletores de posts/reels
            elements = page.query_selector_all("a[href*='/reel/'], a[href*='/p/']")
            for el in elements:
                href = el.get_attribute("href")
                if href:
                    clean_url = f"https://www.instagram.com{href}".split("?")[0]
                    if clean_url not in posts_urls:
                        posts_urls.append(clean_url)
            
            if len(posts_urls) >= target_count:
                break
            page.mouse.wheel(0, 800)
            time.sleep(2)

        # Se encontrou posts nesta rota, não precisa testar a próxima
        if posts_urls:
            print(f"✅ Encontrados {len(posts_urls)} posts na rota {route}")
            break

    return posts_urls[:target_count]
