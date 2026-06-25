__version__ = "2.0"
import os, json, threading
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.metrics import dp

Window.softinput_mode = "pan"

_FONT = "DejaVuSans.ttf"
if os.path.exists(_FONT):
    LabelBase.register(name="Roboto", fn_regular=_FONT)

try:
    import requests
    HAVE_REQUESTS = True
except Exception:
    HAVE_REQUESTS = False
import urllib.request

try:
    from pybit.unified_trading import HTTP
    bybit = HTTP(testnet=False)
except Exception:
    bybit = None

# Голосовой ввод через Android (движок Google)
HAVE_VOICE = False
try:
    from jnius import autoclass
    from android import activity as _android_activity
    _PythonActivity = autoclass('org.kivy.android.PythonActivity')
    _Intent = autoclass('android.content.Intent')
    _Recognizer = autoclass('android.speech.RecognizerIntent')
    HAVE_VOICE = True
except Exception:
    HAVE_VOICE = False

VOICE_REQ = 7001

DS_URL = "https://api.deepseek.com/chat/completions"
TV_URL = "https://api.tavily.com/search"
MODEL_FAST = "deepseek-chat"
MODEL_SMART = "deepseek-reasoner"
SMART = ["почему","проанализир","разбер","сравни","объясни подробно","стратеги",
         "посчитай","реши","докажи","в чём разница","плюсы и минусы"]
WEB = ["сегодня","сейчас","новост","последн","свеж","актуальн","происходит","погода","2026"]
SYSTEM = "Ты полезный ассистент. Отвечай по-русски, ясно и по делу."

class Assistant(App):
    def build(self):
        self.title = "Мой ассистент"
        self.mode = "чат"
        self.ds_path = os.path.join(self.user_data_dir, "ds_key.txt")
        self.tv_path = os.path.join(self.user_data_dir, "tv_key.txt")
        self.cv_path = os.path.join(self.user_data_dir, "convos.json")
        self.ds_key = self._load(self.ds_path)
        self.tv_key = self._load(self.tv_path)
        self.ex_out = "Биржа. Напиши монету (BTC, ETH, SOL) и нажми «Отправить»."
        self._guard = False  # защита окна вывода от правок
        self._load_convos()

        if HAVE_VOICE:
            try: _android_activity.bind(on_activity_result=self._on_activity_result)
            except Exception: pass

        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        tabs = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        for name in ("Чат","Биржа"):
            b = Button(text=name, font_size=dp(16))
            b.bind(on_press=lambda w,n=name: self._set_mode(n))
            tabs.add_widget(b)
        root.add_widget(tabs)

        self.actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        root.add_widget(self.actions)

        # ОКНО ВЫВОДА: обычный TextInput (выделяется → родное «Копировать»),
        # но защищён от случайных правок (текст возвращается назад).
        self.display = TextInput(text="", font_size=dp(16), size_hint_y=1,
                                 background_color=(0.08,0.08,0.08,1),
                                 foreground_color=(1,1,1,1),
                                 cursor_color=(1,1,1,1))
        self.display.bind(text=self._guard_text)
        root.add_widget(self.display)

        self.inp = TextInput(hint_text="Напиши сообщение...", multiline=False,
                             size_hint_y=None, height=dp(50), font_size=dp(18),
                             input_type="text")
        self.inp.bind(on_text_validate=lambda *_: self.go())
        root.add_widget(self.inp)

        bottom = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(4))
        self.mic = Button(text="Голос", size_hint_x=None, width=dp(90), font_size=dp(16))
        self.mic.bind(on_press=lambda *_: self._listen())
        self.btn = Button(text="Отправить", font_size=dp(18))
        self.btn.bind(on_press=lambda *_: self.go())
        bottom.add_widget(self.mic); bottom.add_widget(self.btn)
        root.add_widget(bottom)

        self._set_mode("Чат")
        if not self.ds_key:
            Clock.schedule_once(lambda *_: self._popup_key("ds"), 0.4)
        return root

    # окно вывода: защита от правок (вернуть текст, если пользователь печатает в нём)
    def _guard_text(self, inst, value):
        if self._guard:
            return
        if value != self._shown:
            self._guard = True
            inst.text = self._shown
            self._guard = False

    def _set_display(self, text):
        self._shown = text
        self._guard = True
        self.display.text = text
        self._guard = False
        self._scroll_end()

    # ---------- ГОЛОС ----------
    def _listen(self):
        if not HAVE_VOICE:
            self._info("Голосовой ввод недоступен на этом устройстве.")
            return
        try:
            intent = _Intent(_Recognizer.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(_Recognizer.EXTRA_LANGUAGE_MODEL, _Recognizer.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(_Recognizer.EXTRA_LANGUAGE, "ru-RU")
            intent.putExtra(_Recognizer.EXTRA_PROMPT, "Говорите...")
            _PythonActivity.mActivity.startActivityForResult(intent, VOICE_REQ)
        except Exception as e:
            self._info("Не удалось включить голос: " + str(e)[:60])

    def _on_activity_result(self, requestCode, resultCode, intent):
        if requestCode != VOICE_REQ or intent is None:
            return
        try:
            res = intent.getStringArrayListExtra(_Recognizer.EXTRA_RESULTS)
            if res and res.size() > 0:
                spoken = res.get(0)
                Clock.schedule_once(lambda *_: self._put_voice(spoken), 0)
        except Exception:
            pass

    def _put_voice(self, spoken):
        self.inp.text = (self.inp.text + " " + spoken).strip()

    def _info(self, msg):
        self._set_display((self._shown + "\n\n[i] " + msg).strip())

    def _load(self, p):
        try:
            with open(p) as f: return f.read().strip()
        except Exception: return ""

    def _save(self, p, k):
        try:
            with open(p,"w") as f: f.write(k.strip())
        except Exception: pass

    def _load_convos(self):
        try:
            with open(self.cv_path) as f:
                d = json.load(f)
                self.convos = d.get("convos") or []
                self.cur = d.get("cur", 0)
        except Exception:
            self.convos = []; self.cur = 0
        if not self.convos:
            self.convos = [{"history":[{"role":"system","content":SYSTEM}]}]; self.cur = 0
        if self.cur >= len(self.convos): self.cur = 0

    def _save_convos(self):
        try:
            with open(self.cv_path,"w") as f:
                json.dump({"convos":self.convos,"cur":self.cur}, f, ensure_ascii=False)
        except Exception: pass

    def _title(self, c):
        for m in c["history"]:
            if m["role"]=="user": return m["content"][:30]
        return "Новый диалог"

    def _set_mode(self, n):
        self.mode = n.lower()
        self.actions.clear_widgets()
        if self.mode == "чат":
            b1 = Button(text="+ Новый"); b1.bind(on_press=lambda *_: self._new_convo())
            b2 = Button(text="Диалоги"); b2.bind(on_press=lambda *_: self._show_list())
            self.actions.add_widget(b1); self.actions.add_widget(b2)
            self.inp.hint_text = "Напиши сообщение..."
            self._render_chat()
        else:
            b = Button(text="Очистить"); b.bind(on_press=lambda *_: self._clear_ex())
            self.actions.add_widget(b)
            self.inp.hint_text = "Монета: BTC, ETH, SOL..."
            self._set_display(self.ex_out)

    def _clear_ex(self):
        self.ex_out = "Биржа очищена. Напиши монету."
        self._set_display(self.ex_out)

    def _new_convo(self):
        self.convos.append({"history":[{"role":"system","content":SYSTEM}]})
        self.cur = len(self.convos)-1; self._save_convos()
        if self.mode!="чат": self._set_mode("Чат")
        else: self._render_chat()

    def _show_list(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        pop = Popup(title="Диалоги", size_hint=(0.95,0.9))
        nb = Button(text="+ Новый диалог", size_hint_y=None, height=dp(50))
        nb.bind(on_press=lambda *_: (pop.dismiss(), self._new_convo()))
        box.add_widget(nb)
        sv = ScrollView()
        inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        inner.bind(minimum_height=inner.setter("height"))
        for i in range(len(self.convos)-1,-1,-1):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
            b = Button(text=self._title(self.convos[i]), font_size=dp(15))
            b.bind(on_press=lambda w,idx=i: self._open(idx, pop))
            row.add_widget(b)
            db = Button(text="🗑", size_hint_x=None, width=dp(52),
                        background_color=(0.6,0.2,0.2,1))
            db.bind(on_press=lambda w,idx=i: self._del_convo(idx, pop))
            row.add_widget(db)
            inner.add_widget(row)
        sv.add_widget(inner); box.add_widget(sv)
        pop.content = box; pop.open()

    def _del_convo(self, idx, pop):
        if len(self.convos) <= 1:
            self.convos = [{"history":[{"role":"system","content":SYSTEM}]}]; self.cur = 0
        else:
            self.convos.pop(idx)
            if self.cur >= len(self.convos): self.cur = len(self.convos)-1
        self._save_convos(); pop.dismiss()
        self._render_chat(); self._show_list()

    def _open(self, idx, pop):
        self.cur = idx; self._save_convos(); pop.dismiss(); self._render_chat()

    def _render_chat(self):
        h = self.convos[self.cur]["history"]; lines=[]
        for m in h:
            if m["role"]=="user": lines.append("Ты:\n"+m["content"])
            elif m["role"]=="assistant": lines.append("Ассистент:\n"+m["content"])
        self._set_display("\n\n".join(lines) if lines else "Новый диалог. Напиши сообщение.")

    def _scroll_end(self):
        def _e(*a):
            try: self.display.cursor = (0, max(0, len(self.display._lines)-1))
            except Exception: pass
        Clock.schedule_once(_e, 0.05)

    def _popup_key(self, kind):
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        lab = "Вставь ключ DeepSeek (sk-...)" if kind=="ds" else "Вставь ключ Tavily (tvly-...)"
        box.add_widget(Label(text=lab, size_hint_y=None, height=dp(70)))
        ti = TextInput(multiline=False, size_hint_y=None, height=dp(50), font_size=dp(16))
        box.add_widget(ti)
        btn = Button(text="Сохранить", size_hint_y=None, height=dp(50)); box.add_widget(btn)
        pop = Popup(title="Ключ", content=box, size_hint=(0.92,0.55))
        def save(*a):
            k = ti.text.strip()
            if k:
                if kind=="ds": self._save(self.ds_path,k); self.ds_key=k
                else: self._save(self.tv_path,k); self.tv_key=k
            pop.dismiss()
        btn.bind(on_press=save); pop.open()

    def go(self):
        text = self.inp.text.strip()
        if not text: return
        if text.lower() in ("забудь","сброс","очисти") and self.mode=="чат":
            self.convos[self.cur]["history"]=[{"role":"system","content":SYSTEM}]
            self.inp.text=""; self._save_convos(); self._render_chat(); return
        self.inp.text=""; self.btn.disabled=True
        if self.mode == "биржа":
            self.ex_out += "\n\n> "+text+"\n...загружаю..."
            self._set_display(self.ex_out)
            threading.Thread(target=self._do_price, args=(text,), daemon=True).start()
        else:
            if not self.ds_key:
                self.btn.disabled=False; self._popup_key("ds"); return
            self.convos[self.cur]["history"].append({"role":"user","content":text})
            self._render_chat()
            self._set_display(self._shown + "\n\nАссистент: думаю...")
            threading.Thread(target=self._do_chat, args=(text,), daemon=True).start()

    def _do_chat(self, text):
        h = self.convos[self.cur]["history"]; low=text.lower()
        web = any(w in low for w in WEB)
        if web and not self.tv_key:
            Clock.schedule_once(lambda *_: self._ask_tv(), 0); return
        msg = text
        if web and self.tv_key:
            info = self._tavily(text)
            if info: msg = "Вопрос: "+text+"\n\nСвежие данные из интернета, ответь кратко своими словами:\n\n"+info
        model = MODEL_SMART if (any(w in low for w in SMART) or len(text)>200) else MODEL_FAST
        h[-1] = {"role":"user","content":msg}
        ans = self._deepseek(h, model)
        h[-1] = {"role":"user","content":text}
        h.append({"role":"assistant","content":ans})
        Clock.schedule_once(lambda *_: self._after_chat(), 0)

    def _ask_tv(self):
        h = self.convos[self.cur]["history"]
        if h and h[-1]["role"]=="user": h.pop()
        self.btn.disabled=False; self._render_chat(); self._popup_key("tv")

    def _after_chat(self):
        self._save_convos(); self._render_chat(); self.btn.disabled=False

    def _tavily(self, query):
        try:
            r = requests.post(TV_URL, json={"api_key":self.tv_key,"query":query,
                              "max_results":5,"include_answer":True}, timeout=60)
            if r.status_code != 200: return None
            j = r.json(); t="Сводка: "+str(j.get("answer",""))+"\n\nИсточники:\n"
            for res in j.get("results",[]):
                t += "- "+res.get("title","")+": "+res.get("content","")[:250]+"\n"
            return t
        except Exception: return None

    def _deepseek(self, history, model):
        payload={"model":model,"messages":history,"stream":False}
        headers={"Authorization":"Bearer "+self.ds_key,"Content-Type":"application/json"}
        try:
            if HAVE_REQUESTS:
                r=requests.post(DS_URL,headers=headers,json=payload,timeout=120)
                if r.status_code!=200: return "Ошибка "+str(r.status_code)+": "+r.text[:150]
                return r.json()["choices"][0]["message"]["content"]
            data=json.dumps(payload).encode()
            req=urllib.request.Request(DS_URL,data=data,headers=headers)
            with urllib.request.urlopen(req,timeout=120) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except Exception as e:
            return "Сбой связи: "+str(e)

    # ---------- БИРЖА ----------
    def _sym(self, coin): return coin.upper().replace("USDT","")+"USDT"

    def _do_price(self, coin):
        if bybit is None: self._res_ex("Биржа недоступна (pybit не загрузился)."); return
        try:
            sym=self._sym(coin.split()[0])
            t=bybit.get_tickers(category="linear",symbol=sym)["result"]["list"][0]
            price=float(t["lastPrice"]); pcnt=float(t["price24hPcnt"])*100
            k=bybit.get_kline(category="linear",symbol=sym,interval="D",limit=30)["result"]["list"]
            closes=[float(x[4]) for x in k][::-1]; ma=sum(closes[-20:])/20; last=closes[-1]
            trend="вверх" if last>ma else "вниз"
            msg=(sym+"  цена "+str(price)+" USDT, за 24ч "+("%+.2f"%pcnt)+"%, средняя20д "+("%.2f"%ma)+", тренд "+trend)
        except Exception as e:
            msg="Не нашёл данные по "+coin+" ("+str(e)[:60]+")"
        self._res_ex(msg)

    def _res_ex(self, msg):
        def u(*a):
            self.ex_out = self.ex_out.replace("...загружаю...","") + msg
            if self.mode=="биржа": self._set_display(self.ex_out)
            self.btn.disabled=False
        Clock.schedule_once(u, 0)

if __name__ == "__main__":
    Assistant().run()
