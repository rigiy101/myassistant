__version__ = "1.2"
import os, json, threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.metrics import dp

# Шрифт с кириллицей: регистрируем как "Roboto" -> русские буквы видны во всех виджетах
_FONT = "DejaVuSans.ttf"
if os.path.exists(_FONT):
    LabelBase.register(name="Roboto", fn_regular=_FONT)

try:
    import requests
    HAVE_REQUESTS = True
except Exception:
    HAVE_REQUESTS = False
import urllib.request

DS_URL = "https://api.deepseek.com/chat/completions"
MODEL_FAST = "deepseek-chat"
MODEL_SMART = "deepseek-reasoner"
SMART_TRIGGERS = ["почему", "проанализир", "разбер", "сравни", "объясни подробно",
                  "стратеги", "посчитай", "реши", "докажи", "в чём разница", "плюсы и минусы"]
SYSTEM = "Ты полезный ассистент. Отвечай по-русски, ясно и по делу."

class Assistant(App):
    def build(self):
        self.title = "Мой ассистент"
        self.key_path = os.path.join(self.user_data_dir, "ds_key.txt")
        self.api_key = self._load_key()
        self.waiting_key = False
        self.history = [{"role": "system", "content": SYSTEM}]

        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))

        self.scroll = ScrollView()
        self.chat = Label(text="", size_hint_y=None, halign="left", valign="top",
                          font_size=dp(17), padding=(dp(6), dp(6)))
        self.chat.bind(width=lambda *_: setattr(self.chat, "text_size", (self.chat.width, None)))
        self.chat.bind(texture_size=lambda *_: setattr(self.chat, "height", self.chat.texture_size[1]))
        self.scroll.add_widget(self.chat)
        root.add_widget(self.scroll)

        self.inp = TextInput(hint_text="Напиши сообщение...", multiline=False,
                             size_hint_y=None, height=dp(50), font_size=dp(18))
        self.inp.bind(on_text_validate=lambda *_: self.send())
        root.add_widget(self.inp)

        self.btn = Button(text="Отправить", size_hint_y=None, height=dp(54), font_size=dp(18))
        self.btn.bind(on_press=lambda *_: self.send())
        root.add_widget(self.btn)

        if not self.api_key:
            Clock.schedule_once(lambda *_: self._ask_key(), 0.3)
        else:
            self._add("Ассистент", "Привет! Я готов. Напиши что-нибудь. (слово «забудь» очистит память)")
        return root

    def _load_key(self):
        try:
            with open(self.key_path) as f:
                return f.read().strip()
        except Exception:
            return ""

    def _save_key(self, k):
        try:
            with open(self.key_path, "w") as f:
                f.write(k.strip())
        except Exception:
            pass

    def _ask_key(self):
        self._add("Ассистент", "Вставь свой ключ DeepSeek в поле внизу и нажми «Отправить». "
                  "Сохраню на телефоне, больше спрашивать не буду.")
        self.inp.hint_text = "Вставь ключ DeepSeek (sk-...)"
        self.waiting_key = True

    def _add(self, who, text):
        self.chat.text += "\n[" + who + "] " + text + "\n"
        Clock.schedule_once(lambda *_: setattr(self.scroll, "scroll_y", 0), 0.1)

    def send(self):
        text = self.inp.text.strip()
        if not text:
            return
        if self.waiting_key:
            self._save_key(text); self.api_key = text; self.waiting_key = False
            self.inp.text = ""; self.inp.hint_text = "Напиши сообщение..."
            self._add("Ассистент", "Ключ сохранён. Спрашивай что угодно.")
            return
        if text.lower() in ("забудь", "сброс", "очисти"):
            self.history = [{"role": "system", "content": SYSTEM}]
            self.inp.text = ""
            self._add("Ассистент", "Память очищена.")
            return
        if not self.api_key:
            self._add("Ассистент", "Сначала нужен ключ DeepSeek.")
            return
        self.inp.text = ""
        self._add("Ты", text)
        self.history.append({"role": "user", "content": text})
        self._add("Ассистент", "думаю...")
        self.btn.disabled = True
        smart = any(w in text.lower() for w in SMART_TRIGGERS) or len(text) > 200
        model = MODEL_SMART if smart else MODEL_FAST
        threading.Thread(target=self._ask_model, args=(model,), daemon=True).start()

    def _ask_model(self, model):
        answer = self._request(model)
        Clock.schedule_once(lambda *_: self._show_answer(answer), 0)

    def _request(self, model):
        payload = {"model": model, "messages": self.history, "stream": False}
        headers = {"Authorization": "Bearer " + self.api_key,
                   "Content-Type": "application/json"}
        try:
            if HAVE_REQUESTS:
                r = requests.post(DS_URL, headers=headers, json=payload, timeout=120)
                if r.status_code != 200:
                    return "Ошибка " + str(r.status_code) + ": " + r.text[:150]
                return r.json()["choices"][0]["message"]["content"]
            else:
                data = json.dumps(payload).encode()
                req = urllib.request.Request(DS_URL, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except Exception as e:
            return "Сбой связи: " + str(e)

    def _show_answer(self, answer):
        self.chat.text = self.chat.text.replace("\n[Ассистент] думаю...\n", "")
        self._add("Ассистент", answer)
        self.history.append({"role": "assistant", "content": answer})
        self.btn.disabled = False

if __name__ == "__main__":
    Assistant().run()
