import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import threading
import sys
import os
import re
import time
import webbrowser
import winreg
import multiprocessing
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =================================================================================
#                               СИСТЕМНЫЕ НАСТРОЙКИ
# =================================================================================

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if getattr(sys, 'frozen', False):
    CURRENT_DIR = os.path.dirname(sys.executable)
else:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_DOWNLOAD_DIR = os.path.join(CURRENT_DIR, "Ficbook_Collections")
HISTORY_FILE = os.path.join(CURRENT_DIR, "history.txt")

LOCAL_TOC_NAME = "– (ОГЛАВЛЕНИЕ) –.txt"
GLOBAL_TOC_NAME = "!ВСЯ_БИБЛИОТЕКА.txt"

STOP_FLAG = False

# =================================================================================
#                               ЛОГИКА (BACKEND)
# =================================================================================

class LoggerOut:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        try:
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, string)
            self.text_widget.see(tk.END)
            self.text_widget.configure(state='disabled')
            self.text_widget.update_idletasks()
        except: pass
        
        if sys.__stdout__ is not None:
            sys.__stdout__.write(string)

    def flush(self): pass

def check_stop():
    if STOP_FLAG:
        print("\n[!!!] ОСТАНОВКА ПО ТРЕБОВАНИЮ... СОХРАНЕНИЕ ДАННЫХ...")
        return True
    return False

def get_chrome_major_version():
    try:
        key_path = r"SOFTWARE\Google\Chrome\BLBeacon"
        for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    return int(winreg.QueryValueEx(key, "version")[0].split('.')[0])
            except: pass
    except: pass
    return None

def init_driver():
    if check_stop(): return None
    print("Запуск браузера Chrome...")
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.page_load_strategy = 'eager'

    version = get_chrome_major_version()
    local_driver = os.path.join(CURRENT_DIR, "chromedriver.exe")
    
    try:
        if os.path.exists(local_driver):
            return uc.Chrome(options=options, use_subprocess=True, driver_executable_path=local_driver, version_main=version if version else 142)
        else:
            return uc.Chrome(options=options, use_subprocess=True, version_main=version if version else None)
    except Exception as e:
        print(f"!!! ОШИБКА ЗАПУСКА ДРАЙВЕРА: {e}")
        return None

def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', '_', name).strip()
    return name.strip()

def load_history():
    if not os.path.exists(HISTORY_FILE): return set()
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except: return set()

def save_to_history(url):
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")
            f.flush()
            os.fsync(f.fileno())
    except: pass

def check_file_exists(url, save_folder):
    if not os.path.exists(save_folder): return False
    try:
        for f in os.listdir(save_folder):
            if f.endswith(".txt") and f != LOCAL_TOC_NAME:
                with open(os.path.join(save_folder, f), "r", encoding="utf-8", errors="ignore") as file:
                    if url in file.read(1024): return True
    except: pass
    return False

def check_and_click_warnings(driver):
    try:
        buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Да, мне есть 18') or contains(text(), 'Продолжить читать') or contains(text(), 'Согласен')]")
        for btn in buttons:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                return True
    except: pass
    return False

def get_fanfic_metadata(driver):
    info_text = ""
    try:
        desc_block = driver.find_element(By.CSS_SELECTOR, "div.description")
        blocks = desc_block.find_elements(By.CSS_SELECTOR, ".mb-10")
        for block in blocks:
            try:
                label = block.find_element(By.TAG_NAME, "strong").text
                content = block.text.replace(label, "").strip()
                content = re.sub(r'\n+', ', ', content)
                info_text += f"{label} {content}\n"
            except: continue
        info_text += "\n" + "-"*20 + "\n\n"
    except: info_text = "Описание не найдено.\n\n"
    
    author = "Unknown"
    try: author = driver.find_element(By.CSS_SELECTOR, ".creator-username").text.strip()
    except: pass
    
    return info_text, author

def get_chapter_title(driver):
    try: return driver.find_element(By.CSS_SELECTOR, "div.title-area h2").text.strip()
    except: pass
    try: return driver.find_element(By.CSS_SELECTOR, "section.part-text h2, h3").text.strip()
    except: return None

def scrape_fanfic(driver, fic_url, save_folder):
    if check_stop(): return False
    driver.get(fic_url)
    time.sleep(1.5)
    check_and_click_warnings(driver)

    if "Фанфик удален" in driver.page_source or "Работа недоступна" in driver.page_source:
        print("    [ERROR] Работа удалена.")
        return False

    try:
        title = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "h1"))).text
    except: return False

    desc_text, author = get_fanfic_metadata(driver)
    
    base_name = f"{title} [{author}]"
    safe_name = sanitize_filename(base_name)
    file_path = os.path.join(save_folder, f"{safe_name}.txt")

    counter = 1
    while os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                if fic_url in f.read(1024): return True 
        except: pass
        safe_name = sanitize_filename(f"{base_name} ({counter})")
        file_path = os.path.join(save_folder, f"{safe_name}.txt")
        counter += 1

    print(f"    Книга: {title} (Автор: {author})")

    try:
        toc = driver.find_elements(By.CSS_SELECTOR, "ul.list-of-fanfic-parts li.part a.part-link")
        if toc:
            driver.execute_script("arguments[0].click();", toc[0])
            time.sleep(2)
    except: pass
    
    check_and_click_warnings(driver)

    try:
        with open(file_path, "w", encoding="utf-8-sig") as f:
            f.write(f"=== {title} ===\nURL: {fic_url}\nАвтор: {author}\n\n")
            f.write(desc_text)
            
            page_num = 1
            while True:
                if check_stop(): return False
                check_and_click_warnings(driver)
                driver.execute_script("document.querySelectorAll('.fb-ads-block, .rkl-block, div[id^=\"adfox\"]').forEach(el => el.remove());")
                
                if "Вы прочли последнюю" in driver.page_source: break

                try:
                    content = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#content, .js-public-beta-text")))
                    chap_title = get_chapter_title(driver)
                    
                    f.write(f"\n\n--- {chap_title if chap_title else f'Глава {page_num}'} ---\n\n")
                    f.write(content.text)
                    print(f"      + Глава {page_num}", end="\r")

                    next_btn = driver.find_elements(By.CSS_SELECTOR, "a.btn-next")
                    if next_btn and next_btn[0].is_displayed():
                        driver.execute_script("arguments[0].click();", next_btn[0])
                        page_num += 1
                        time.sleep(1.5)
                    else: break
                except: 
                    driver.refresh()
                    time.sleep(3)
                    try: WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#content"))); continue
                    except: break
        return True
    except Exception as e:
        print(f"    Ошибка записи: {e}")
        return False

def get_collection_links(driver, col_url):
    links = []
    base_url = col_url.split('?')[0]
    
    driver.get(base_url)
    time.sleep(2)
    try:
        header = driver.find_element(By.TAG_NAME, "body").text
        total = int(re.search(r"В сборнике\s+(\d+)\s+фанфик", header).group(1))
        print(f"  [INFO] Ожидается работ: {total}")
    except: pass

    page = 1
    print("  Сбор ссылок...", end="")
    while True:
        if check_stop(): return links
        
        url = f"{base_url}?p={page}"
        driver.get(url)
        
        if "доступ к сайту временно ограничен" in driver.page_source:
            print("\n  [PAUSE] Бан IP. Жду 60 сек...")
            for _ in range(60): 
                time.sleep(1)
                if check_stop(): return links
            driver.refresh()
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")

        try:
            WebDriverWait(driver, 8).until(lambda d: d.find_elements(By.CSS_SELECTOR, "a.visit-link") or d.find_elements(By.XPATH, "//div[contains(text(), 'В этом сборнике нет работ')]"))
        except: 
            print(" [R]", end="")
            driver.refresh()
            time.sleep(5)
            try: WebDriverWait(driver, 8).until(lambda d: d.find_elements(By.CSS_SELECTOR, "a.visit-link")); 
            except: break

        elements = driver.find_elements(By.CSS_SELECTOR, "a.visit-link")
        if not elements: 
             elements = driver.find_elements(By.XPATH, "//h3[contains(@class, 'fanfic-inline-title')]/a")
        
        if not elements: break
        
        new_on_page = 0
        for el in elements:
            href = el.get_attribute("href")
            if href and href not in links:
                links.append(href)
                new_on_page += 1
        
        if new_on_page == 0: break
        print(f" {page}", end="", flush=True)
        page += 1
        time.sleep(3)

        try:
            next_exists = driver.find_elements(By.XPATH, f"//div[contains(@class, 'pagination')]//a[contains(@href, '?p={page}')]")
            if not next_exists and page > 1:
                arrow = driver.find_elements(By.CSS_SELECTOR, "a.arrow svg.arrow-right")
                if not arrow: break
                if arrow[0].find_element(By.XPATH, "./..").tag_name != 'a': break
        except: pass

    print(f"\n  Найдено ссылок: {len(links)}")
    return links

def rebuild_toc_func(folder_path):
    library = {}
    
    old_names = ["_ОГЛАВЛЕНИЕ.txt", "!ОГЛАВЛЕНИЕ.txt", "00_ОГЛАВЛЕНИЕ.txt", "!_00_ОГЛАВЛЕНИЕ.txt", LOCAL_TOC_NAME]
    for old_name in old_names:
        if old_name == LOCAL_TOC_NAME: continue
        try: 
            p = os.path.join(folder_path, old_name)
            if os.path.exists(p): os.remove(p)
        except: pass

    files = [f for f in os.listdir(folder_path) if f.endswith(".txt") and f != LOCAL_TOC_NAME]
    if not files: return 0

    for filename in files:
        filepath = os.path.join(folder_path, filename)
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [f.readline().strip() for _ in range(50)]
            
            title = filename.replace(".txt", "")
            match = re.match(r"(.*) \[(.*)\]", title)
            if match: title = match.group(1).strip(); file_author = match.group(2).strip()
            else: file_author = ""

            fandom, pairing, text_author = "Разное", "", ""
            for line in lines:
                if line.startswith("Фэндом:"): fandom = line.replace("Фэндом:", "").strip()
                elif line.startswith("Вселенная:") and fandom == "Разное": fandom = line.replace("Вселенная:", "").strip()
                if line.startswith("Пэйринг и персонажи:"): pairing = line.replace("Пэйринг и персонажи:", "").strip()
                if line.startswith("Автор:"): text_author = line.replace("Автор:", "").strip()
            
            final_author = text_author if text_author else file_author
            if fandom not in library: library[fandom] = []
            
            entry = title
            if final_author: entry += f" (Авт. {final_author})"
            if pairing: entry += f" [{pairing[:150] + '...' if len(pairing)>150 else pairing}]"
            
            library[fandom].append(entry)
        except: continue

    try:
        with open(os.path.join(folder_path, LOCAL_TOC_NAME), "w", encoding="utf-8-sig") as f:
            for fam in sorted(library.keys()):
                f.write(f"=== [{fam}] ===\n")
                for book in sorted(library[fam]): f.write(f"{book}\n")
                f.write("\n")
    except: pass
    
    return len(files)

def make_global_toc_func():
    outfile = os.path.join(BASE_DOWNLOAD_DIR, GLOBAL_TOC_NAME)
    if not os.path.exists(BASE_DOWNLOAD_DIR): return

    with open(outfile, "w", encoding="utf-8-sig") as glob:
        glob.write(f"БИБЛИОТЕКА FICBOOK\nОбновлено: {time.strftime('%Y-%m-%d %H:%M')}\n\n")
        for col in sorted(os.listdir(BASE_DOWNLOAD_DIR)):
            col_path = os.path.join(BASE_DOWNLOAD_DIR, col)
            if os.path.isdir(col_path):
                local_toc = os.path.join(col_path, LOCAL_TOC_NAME)
                if os.path.exists(local_toc):
                    glob.write(f"{'='*30}\n📂 СБОРНИК: {col.upper()}\n{'='*30}\n")
                    with open(local_toc, "r", encoding="utf-8-sig") as loc:
                        glob.write(loc.read() + "\n\n")

def scan_entire_disk_for_links():
    """Сканирует все .txt файлы во всех папках и возвращает карту {URL: Путь}"""
    print("Глобальное сканирование диска... Подождите.")
    disk_map = {}
    if not os.path.exists(BASE_DOWNLOAD_DIR): return disk_map

    for root, _, files in os.walk(BASE_DOWNLOAD_DIR):
        for filename in files:
            if filename.endswith(".txt") and not filename.startswith("!") and filename != LOCAL_TOC_NAME:
                try:
                    path = os.path.join(root, filename)
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for _ in range(10):
                            line = f.readline()
                            if "URL:" in line:
                                url = line.replace("URL:", "").strip()
                                # Очистка URL
                                if "#" in url: url = url.split("#")[0]
                                if "?" in url: url = url.split("?")[0]
                                disk_map[url] = os.path.basename(root) # Сохраняем имя папки
                                break
                except: pass
    print(f"Проиндексировано {len(disk_map)} работ на диске.")
    return disk_map

# =================================================================================
#                               ГРАФИЧЕСКИЙ ИНТЕРФЕЙС
# =================================================================================

class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command, icon="", bg_color="#4A90E2", hover_color="#357ABD", **kwargs):
        super().__init__(parent, height=60, highlightthickness=0, **kwargs)
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text = text
        self.icon = icon
        self.enabled = True
        
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        
        self.draw()
    
    def draw(self):
        self.delete("all")
        width = self.winfo_width() if self.winfo_width() > 1 else 200
        height = 60
        
        color = self.hover_color if hasattr(self, '_hover') and self._hover else self.bg_color
        if not self.enabled:
            color = "#CCCCCC"
        
        r = 10
        self.create_arc(0, 0, r*2, r*2, start=90, extent=90, fill=color, outline="")
        self.create_arc(width-r*2, 0, width, r*2, start=0, extent=90, fill=color, outline="")
        self.create_arc(0, height-r*2, r*2, height, start=180, extent=90, fill=color, outline="")
        self.create_arc(width-r*2, height-r*2, width, height, start=270, extent=90, fill=color, outline="")
        
        self.create_rectangle(r, 0, width-r, height, fill=color, outline="")
        self.create_rectangle(0, r, width, height-r, fill=color, outline="")
        
        full_text = f"{self.icon} {self.text}" if self.icon else self.text
        text_color = "white" if self.enabled else "#666666"
        self.create_text(width/2, height/2, text=full_text, fill=text_color, 
                        font=("Segoe UI", 11, "bold"), tags="text")
    
    def _on_click(self, event):
        if self.enabled and self.command:
            self.command()
    
    def _on_enter(self, event):
        self._hover = True
        self.draw()
    
    def _on_leave(self, event):
        self._hover = False
        self.draw()
    
    def configure_state(self, state):
        self.enabled = (state == "normal")
        self.draw()

class FicbookApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MyFicbook 1.1")
        self.geometry("800x700")
        self.configure(bg="#F5F7FA")
        
        try:
            icon_path = resource_path("feather.ico")
            self.iconbitmap(icon_path)
        except: pass

        self.driver = None
        self.is_running = False
        
        self.create_header()
        self.create_info_panel()
        self.create_button_panel()
        self.create_console()
        
        sys.stdout = LoggerOut(self.console)
        self.update_folder_stats()

    def create_header(self):
        header_frame = tk.Frame(self, bg="#2C3E50", height=60)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        left_frame = tk.Frame(header_frame, bg="#2C3E50")
        left_frame.pack(side=tk.LEFT, padx=15, fill=tk.Y)
        
        tk.Label(left_frame, text="📚 MyFicbook", font=("Segoe UI", 16, "bold"), 
                bg="#2C3E50", fg="white").pack(side=tk.LEFT, pady=10)

        self.stats_label = tk.Label(header_frame, text="Загрузка статистики...", font=("Segoe UI", 11), 
                                   bg="#2C3E50", fg="#BDC3C7")
        self.stats_label.pack(side=tk.RIGHT, padx=20)

    def create_info_panel(self):
        info_container = tk.Frame(self, bg="#F5F7FA")
        info_container.pack(fill=tk.X, padx=20, pady=(15, 0))
        
        self.info_text = tk.Text(info_container, height=10, font=("Segoe UI", 10), 
                                bg="#F5F7FA", fg="#2C3E50", relief=tk.FLAT, wrap=tk.WORD,
                                bd=0, highlightthickness=0)
        self.info_text.pack(fill=tk.BOTH)
        
        self.info_text.tag_configure("item", lmargin1=0, lmargin2=35, tabs=[35], spacing3=10)
        self.info_text.tag_configure("bold", font=("Segoe UI", 10, "bold"))
        self.info_text.tag_configure("link", foreground="#4A90E2", underline=True)
        
        self.info_text.tag_bind("link", "<Button-1>", lambda e: webbrowser.open_new("https://t.me/SnyppiVPN_bot"))
        self.info_text.tag_bind("link", "<Enter>", lambda e: self.info_text.config(cursor="hand2"))
        self.info_text.tag_bind("link", "<Leave>", lambda e: self.info_text.config(cursor="arrow"))

        data = [
            ("📥", "Скачать (Синхронизация)", "Основной режим. Заходит в аккаунт, сравнивает сборники с диском. Скачивает новые добавленные работы."),
            ("📑", "Обновить оглавления", "Сканирует файлы в папках и пересоздает файлы оглавлений во всех сборниках."),
            ("🔍", "Сравнить с сайтом", "Показывает, какие фанфики были недокачаны или наоборот скачаны, но удалены с сайта."),
            ("⛔", "Стоп", "Безопасная остановка. Сохраняет текущую книгу перед выходом и формирует оглавление."),
            ("⚠️", "Внимание", "VPN"),
            ("✉️", "Обратная связь", "EMAIL")
        ]

        for icon, title, desc in data:
            self.info_text.insert(tk.END, f"{icon}\t", "item")
            self.info_text.insert(tk.END, title, ("item", "bold"))
            
            if desc == "VPN":
                self.info_text.insert(tk.END, " - Для работы сайта может потребоваться ВПН. Рекомендуем - ", "item")
                self.info_text.insert(tk.END, "@SnyppiVPN_bot\n", ("item", "link", "bold"))
            elif desc == "EMAIL":
                self.info_text.insert(tk.END, " - Предложения и ошибки в работе можете направить на почту ", "item")
                self.info_text.insert(tk.END, "1snyppi@gmail.com\n", ("item", "bold"))
            else:
                self.info_text.insert(tk.END, f" - {desc}\n", "item")
            
        self.info_text.configure(state="disabled")

    def create_button_panel(self):
        btn_container = tk.Frame(self, bg="#F5F7FA")
        btn_container.pack(fill=tk.X, padx=15, pady=(5, 5))
        
        row1 = tk.Frame(btn_container, bg="#F5F7FA")
        row1.pack(fill=tk.X, pady=(0, 10))
        
        self.btn_download = ModernButton(row1, "Скачать (Синхронизация)", self.start_download,
                                        icon="📥", bg_color="#4A90E2", hover_color="#357ABD", width=380)
        self.btn_download.pack(side=tk.LEFT, padx=(0, 10), fill=tk.BOTH, expand=True)
        self.btn_download.bind("<Configure>", lambda e: self.btn_download.draw())
        
        self.btn_toc = ModernButton(row1, "Обновить оглавления", self.start_toc_rebuild,
                                   icon="📑", bg_color="#27AE60", hover_color="#229954", width=380)
        self.btn_toc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.btn_toc.bind("<Configure>", lambda e: self.btn_toc.draw())
        
        row2 = tk.Frame(btn_container, bg="#F5F7FA")
        row2.pack(fill=tk.X)
        
        self.btn_audit = ModernButton(row2, "Сравнить с сайтом", self.start_audit,
                                     icon="🔍", bg_color="#E67E22", hover_color="#CA6F1E", width=380)
        self.btn_audit.pack(side=tk.LEFT, padx=(0, 10), fill=tk.BOTH, expand=True)
        self.btn_audit.bind("<Configure>", lambda e: self.btn_audit.draw())
        
        self.btn_stop = ModernButton(row2, "СТОП", self.stop_process,
                                    icon="⛔", bg_color="#E74C3C", hover_color="#C0392B", width=380)
        self.btn_stop.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.btn_stop.bind("<Configure>", lambda e: self.btn_stop.draw())
        self.btn_stop.configure_state("disabled")

    def create_console(self):
        console_container = tk.Frame(self, bg="#F5F7FA")
        console_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        lbl = tk.Label(console_container, text="Журнал событий:", font=("Segoe UI", 10, "bold"), bg="#F5F7FA", fg="#34495E")
        lbl.pack(anchor=tk.W, pady=(0, 5))
        
        self.console = scrolledtext.ScrolledText(console_container, state='disabled', 
                                                font=("Consolas", 9),
                                                bg="#1E1E1E", fg="#D4D4D4", 
                                                insertbackground="white",
                                                relief=tk.FLAT,
                                                padx=10, pady=10)
        self.console.pack(fill=tk.BOTH, expand=True)
        
        # КОНТЕКСТНОЕ МЕНЮ (Копирование)
        self.context_menu = tk.Menu(self.console, tearoff=0)
        self.context_menu.add_command(label="Копировать", command=self.copy_selection)
        self.console.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    def copy_selection(self):
        try:
            selected_text = self.console.get("sel.first", "sel.last")
            self.clipboard_clear()
            self.clipboard_append(selected_text)
        except: pass

    def set_running(self, running):
        global STOP_FLAG
        state = "disabled" if running else "normal"
        stop_state = "normal" if running else "disabled"
        if running: STOP_FLAG = False
        
        self.btn_download.configure_state(state)
        self.btn_toc.configure_state(state)
        self.btn_audit.configure_state(state)
        self.btn_stop.configure_state(stop_state)

    def stop_process(self):
        if messagebox.askyesno("Остановка", "Прервать процесс?"):
            global STOP_FLAG
            STOP_FLAG = True
            print("\n!!! ПОЛУЧЕН СИГНАЛ ОСТАНОВКИ !!!")

    def update_folder_stats(self):
        if not os.path.exists(BASE_DOWNLOAD_DIR):
            self.stats_label.config(text="Папка не создана")
            return
        
        cols = 0
        books = 0
        for d in os.listdir(BASE_DOWNLOAD_DIR):
            path = os.path.join(BASE_DOWNLOAD_DIR, d)
            if os.path.isdir(path):
                cols += 1
                books += len([f for f in os.listdir(path) if f.endswith(".txt") and f != LOCAL_TOC_NAME])
        
        self.stats_label.config(text=f"Сборников: {cols} | Книг: {books}")

    def run_task(self, task_func):
        self.set_running(True)
        thread = threading.Thread(target=self._wrapper, args=(task_func,))
        thread.start()

    def _wrapper(self, func):
        try:
            func()
            self.update_folder_stats()
        except Exception as e:
            print(f"Критическая ошибка потока: {e}")
        finally:
            if self.driver:
                try: self.driver.quit()
                except: pass
                self.driver = None
            self.set_running(False)
            print("\n--- Завершено ---")

    def start_download(self):
        def show_custom_message(parent, title, message, btn_text):
            dialog = tk.Toplevel(parent)
            dialog.title(title)
            try: dialog.iconbitmap(resource_path("feather.ico"))
            except: pass
            w, h = 450, 220
            x = parent.winfo_x() + (parent.winfo_width() // 2) - (w // 2)
            y = parent.winfo_y() + (parent.winfo_height() // 2) - (h // 2)
            dialog.geometry(f"{w}x{h}+{x}+{y}")
            dialog.configure(bg="white")
            dialog.resizable(False, False)
            dialog.transient(parent)
            dialog.grab_set()
            content = tk.Frame(dialog, bg="white", padx=25, pady=25)
            content.pack(fill="both", expand=True)
            icon_canvas = tk.Canvas(content, width=48, height=48, bg="white", highlightthickness=0)
            icon_canvas.pack(side=tk.LEFT, anchor="n", padx=(0, 20))
            icon_canvas.create_oval(2, 2, 46, 46, fill="#4A90E2", outline="")
            icon_canvas.create_text(24, 24, text="i", fill="white", font=("Times New Roman", 28, "bold italic"))
            lbl = tk.Label(content, text=message, font=("Segoe UI", 11), justify=tk.LEFT, bg="white", anchor="w", wraplength=330)
            lbl.pack(side=tk.LEFT, fill="both", expand=True)
            btn_frame = tk.Frame(dialog, bg="#F5F7FA", pady=15)
            btn_frame.pack(fill="x", side=tk.BOTTOM)
            btn = tk.Button(btn_frame, text=btn_text, command=dialog.destroy, font=("Segoe UI", 10), width=15, bg="#E1E1E1", relief="groove", cursor="hand2")
            btn.pack()
            btn.focus_set()
            parent.wait_window(dialog)
        show_custom_message(self, "Инструкция", "Сейчас откроется браузер.\n\n1. Введите ваш логин и пароль на сайте.\n2. Вернитесь в программу и подтвердите вход.", "Понятно")
        self.run_task(self.task_download)

    def task_download(self):
        self.driver = init_driver()
        if not self.driver: return
        
        try:
            self.driver.get("https://ficbook.net/login")
            if check_stop(): return
            messagebox.showinfo("Жду входа", "Вы залогинились? Нажмите ОК для старта.")
            
            print("Сканирую сборники...")
            self.driver.get("https://ficbook.net/home/collections")
            
            try: WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.collection-thumb-info a")))
            except: print("Сборники не найдены."); return

            col_elems = self.driver.find_elements(By.CSS_SELECTOR, "div.collection-thumb-info > a")
            collections = []
            for el in col_elems:
                if "/collections/" in el.get_attribute("href"):
                    collections.append({"name": el.text, "url": el.get_attribute("href")})

            print(f"Найдено сборников: {len(collections)}")
            downloaded_urls = load_history()

            for idx, col in enumerate(collections, 1):
                if check_stop(): break
                safe_name = sanitize_filename(col['name'])
                print(f"\n=== [{idx}/{len(collections)}] {col['name']} ===")
                folder = os.path.join(BASE_DOWNLOAD_DIR, safe_name)
                if not os.path.exists(folder): os.makedirs(folder)
                
                links = get_collection_links(self.driver, col['url'])
                if not links: continue

                print(f"  Обработка {len(links)} работ...")
                
                for i, url in enumerate(links):
                    if check_stop(): break
                    if url in downloaded_urls: continue
                    if check_file_exists(url, folder):
                        save_to_history(url)
                        downloaded_urls.add(url)
                        continue

                    print(f"  [{i+1}/{len(links)}]", end="")
                    if scrape_fanfic(self.driver, url, folder):
                        save_to_history(url)
                        downloaded_urls.add(url)
                        time.sleep(1)
                
                rebuild_toc_func(folder)
            
            print("\nОбновляю глобальное оглавление...")
            make_global_toc_func()

        except Exception as e:
            print(f"Ошибка: {e}")

    def start_toc_rebuild(self):
        self.run_task(self.task_toc)

    def task_toc(self):
        print("Пересоздание всех оглавлений...")
        if not os.path.exists(BASE_DOWNLOAD_DIR): 
            print("Папка пуста.")
            return
        
        for d in os.listdir(BASE_DOWNLOAD_DIR):
            if check_stop(): break
            path = os.path.join(BASE_DOWNLOAD_DIR, d)
            if os.path.isdir(path):
                cnt = rebuild_toc_func(path)
                print(f"OK: {d} ({cnt} книг)")
        
        make_global_toc_func()
        print("Глобальное оглавление обновлено.")

    def start_audit(self):
        if not os.path.exists(BASE_DOWNLOAD_DIR):
            messagebox.showerror("Ошибка", "Папка с коллекциями не найдена.")
            return

        folders = [f for f in os.listdir(BASE_DOWNLOAD_DIR) if os.path.isdir(os.path.join(BASE_DOWNLOAD_DIR, f))]
        folders.sort()
        
        if not folders:
            messagebox.showinfo("Пусто", "Нет скачанных сборников.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Выбор сборника")
        try: dialog.iconbitmap(resource_path("feather.ico"))
        except: pass
        dialog.geometry("450x180")
        dialog.configure(bg="#F5F7FA")
        dialog.transient(self)
        dialog.grab_set()
        content = tk.Frame(dialog, bg="white")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        tk.Label(content, text="Выберите сборник для проверки:", font=("Segoe UI", 11, "bold"), bg="white", fg="#34495E").pack(pady=(0, 15))
        combo = ttk.Combobox(content, values=["[ПРОВЕРИТЬ ВСЕ]"] + folders, state="readonly", width=50, font=("Segoe UI", 10))
        combo.current(0)
        combo.pack(pady=5)
        def on_confirm():
            selection = combo.get()
            dialog.destroy()
            if selection == "[ПРОВЕРИТЬ ВСЕ]": self.audit_target = ""
            else: self.audit_target = selection
            self.run_task(self.task_audit)
        btn_frame = tk.Frame(content, bg="white")
        btn_frame.pack(pady=(15, 0))
        confirm_btn = tk.Button(btn_frame, text="Начать аудит", command=on_confirm, font=("Segoe UI", 10, "bold"), bg="#4A90E2", fg="white", relief=tk.FLAT, padx=30, pady=10, cursor="hand2")
        confirm_btn.pack()

    def task_audit(self):
        self.driver = init_driver()
        try:
            self.driver.get("https://ficbook.net/login")
            messagebox.showinfo("Аудит", "Войдите и нажмите ОК.")
            
            self.driver.get("https://ficbook.net/home/collections")
            try: WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.collection-thumb-info a")))
            except: return

            col_elems = self.driver.find_elements(By.CSS_SELECTOR, "div.collection-thumb-info > a")
            collections = []
            for el in col_elems:
                if "/collections/" in el.get_attribute("href"):
                    collections.append({"name": el.text, "url": el.get_attribute("href")})

            if self.audit_target:
                collections = [c for c in collections if c['name'] == self.audit_target]
                if not collections:
                    print(f"Сборник '{self.audit_target}' не найден на сайте.")
                    return

            print("Индексация всей библиотеки...")
            global_disk_map = scan_entire_disk_for_links()

            total_missing = 0
            report_lines = []

            for col in collections:
                if check_stop(): break
                print(f"\n--- АУДИТ: {col['name']} ---")
                folder = os.path.join(BASE_DOWNLOAD_DIR, sanitize_filename(col['name']))
                
                site_links = set(get_collection_links(self.driver, col['url']))
                clean_site_links = {u.split('?')[0].split('#')[0] for u in site_links}
                
                local_urls = set()
                if os.path.exists(folder):
                    for f in os.listdir(folder):
                        if f.endswith(".txt") and f != LOCAL_TOC_NAME:
                            try:
                                with open(os.path.join(folder, f), "r", encoding="utf-8", errors="ignore") as file:
                                    for _ in range(10):
                                        l = file.readline()
                                        if "URL:" in l: 
                                            u = l.replace("URL:", "").strip()
                                            if "#" in u: u = u.split("#")[0]
                                            if "?" in u: u = u.split("?")[0]
                                            local_urls.add(u)
                            except: pass

                found_locally = 0
                found_elsewhere = 0
                truly_missing = []
                
                for url in site_links:
                    clean_url = url.split("?")[0].split("#")[0]
                    if clean_url in local_urls:
                        found_locally += 1
                    elif clean_url in global_disk_map:
                        found_elsewhere += 1
                    else:
                        truly_missing.append(url)
                
                # Поиск раритетов (есть на диске, нет на сайте)
                extra_files = local_urls - clean_site_links

                print(f"Сайт: {len(site_links)} | В папке: {found_locally} | В других: {found_elsewhere} | Нет нигде: {len(truly_missing)}")
                
                # ОТЧЕТ: НЕТ НА ДИСКЕ
                if truly_missing:
                    report_lines.append(f"\n=== {col['name']} (ОТСУТСТВУЮТ) ===")
                    for lnk in truly_missing:
                        if check_stop(): break
                        self.driver.get(lnk)
                        status = "ЖИВОЙ (Скачать)"
                        if "удален" in self.driver.page_source or "недоступна" in self.driver.page_source: status = "УДАЛЕН АВТОРОМ"
                        elif "ограничен" in self.driver.page_source: status = "ОГРАНИЧЕН АВТОРОМ"
                        
                        print(f" -> {lnk} [{status}]")
                        report_lines.append(f"{lnk} -> {status}")
                        time.sleep(1)
                    total_missing += len(truly_missing)
                
                # ОТЧЕТ: НЕТ НА САЙТЕ (РАРИТЕТЫ)
                if extra_files:
                    print(f"  [!] Найдено {len(extra_files)} файлов, удаленных из сборника")
                    report_lines.append(f"\n=== {col['name']} (СКАЧАНО, НЕТ В СБОРНИКЕ НА САЙТЕ) ===")
                    for u in extra_files:
                        fname = "Unknown.txt"
                        for f in os.listdir(folder):
                             try:
                                with open(os.path.join(folder, f), "r", encoding="utf-8", errors="ignore") as file:
                                    if u in file.read(1024): 
                                        fname = f
                                        break
                             except: pass
                        report_lines.append(f"{fname} -> {u}")

            if report_lines:
                # 1. ЗАПИСЬ В ФАЙЛ
                # Файл создается рядом с программой
                report_path = os.path.join(CURRENT_DIR, "AUDIT_REPORT.txt")
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(report_lines))
                
                # 2. ВЫВОД В ЖУРНАЛ (ЭКРАН)
                print("\n" + "="*30)
                print("ИТОГИ АУДИТА:")
                print("="*30)
                for line in report_lines:
                    print(line)
                print("\n" + "="*30)
                
                print(f"\nКопия отчета сохранена в: {report_path}") # Пишем путь к файлу
                messagebox.showinfo("Готово", f"Аудит завершен.\nРезультаты в журнале и в файле AUDIT_REPORT.txt")
            else:
                print("\nАудит завершен. Библиотека идеальна!")
                messagebox.showinfo("Готово", "Расхождений не найдено.")

        except Exception as e:
            print(f"Ошибка аудита: {e}")


# --- ФУНКЦИЯ ГЛОБАЛЬНОГО ПОИСКА ---
def scan_entire_disk_for_links():
    disk_map = {} # {URL: FolderName}
    for root, _, files in os.walk(BASE_DOWNLOAD_DIR):
        for filename in files:
            if filename.endswith(".txt") and not filename.startswith("!") and filename != LOCAL_TOC_NAME:
                try:
                    path = os.path.join(root, filename)
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for _ in range(10):
                            line = f.readline()
                            if "URL:" in line:
                                url = line.replace("URL:", "").strip()
                                if "#" in url: url = url.split("#")[0]
                                if "?" in url: url = url.split("?")[0]
                                disk_map[url] = os.path.basename(root)
                                break
                except: pass
    return disk_map

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = FicbookApp()
    app.mainloop()