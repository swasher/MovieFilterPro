import time

import rtfox_browser as uc

URL = "https://kinozal.guru/browse.php?s=&g=0&c=1002&v=7&d=0&w=0&t=0&f=0"


def main():
    driver = uc.Chrome()
    try:
        driver.get(URL)

        for _ in range(90):
            title = driver.title
            url = driver.current_url
            if "moment" not in title.lower() and "Один момент" not in title and "challenge" not in url.lower():
                break
            time.sleep(1)

        print("URL:", driver.current_url)
        print("TITLE:", driver.title)
        print("LEN:", len(driver.page_source))

        with open("page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()