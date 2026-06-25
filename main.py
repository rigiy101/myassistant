__version__ = "1.7"
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

INTERVAL="240"; CANDLES=1500; ATR_LEN=14; MAXH=300; MULT=3.0; COST_RT=0.0012; DON=20
TREND_COIN="BTC"; FLAT_COIN="DOGE"

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
        self.test_out = "Тест. Напиши стратегию (тренд / отбой / пробой) — прогоню на BTC и DOGE."
        self._load_convos()

        if HAVE_VOICE:
            try: _android_activity.bind(on_activity_result=self._on_activity_result)
            except Exception: pass

        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        tabs = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        for name in ("Чат","Биржа","Тест"):
            b = Button(text=name, font_size=dp(16))
            b.bind(on_press=lambda w,n=name: self._set_mode(n))
            tabs.add_widget(b)
        root.add_widget(tabs)

        self.actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        root.add_widget(self.actions)

        self.display = TextInput(text="", readonly=True, font_size=dp(16))
        root.add_widget(self.display)

        self.inp = TextInput(hint_text="Напиши сообщение...", multiline=False,
                             size_hint_y=None, height=dp(50), font_size=dp(18))
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

    # ---------- ГОЛОС ----------
    def _listen(self):
        if not HAVE_VOICE:
            self._toast("Голосовой ввод недоступен на этом устройстве.")
            return
        try:
            intent = _Intent(_Recognizer.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(_Recognizer.EXTRA_LANGUAGE_MODEL, _Recognizer.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(_Recognizer.EXTRA_LANGUAGE, "ru-RU")
            intent.putExtra(_Recognizer.EXTRA_PROMPT, "Говорите...")
            _PythonActivity.mActivity.startActivityForResult(intent, VOICE_REQ)
        except Exception as e:
            self._toast("Не удалось включить голос: " + str(e)[:60])

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

    def _toast(self, msg):
        self.display.text = (self.display.text + "\n\n[i] " + msg).strip()
        self._scroll_end()

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
        elif self.mode == "биржа":
            b = Button(text="Очистить"); b.bind(on_press=lambda *_: self._clear("ex"))
            self.actions.add_widget(b)
            self.inp.hint_text = "Монета: BTC, ETH, SOL..."
            self.display.text = self.ex_out
        else:
            b = Button(text="Очистить"); b.bind(on_press=lambda *_: self._clear("test"))
            self.actions.add_widget(b)
            self.inp.hint_text = "Стратегия: тренд / отбой / пробой"
            self.display.text = self.test_out

    def _clear(self, which):
        if which=="ex": self.ex_out="Биржа очищена. Напиши монету."; self.display.text=self.ex_out
        else: self.test_out="Тест очищен. Напиши стратегию."; self.display.text=self.test_out

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
            b = Button(text=self._title(self.convos[i]), size_hint_y=None, height=dp(48))
            b.bind(on_press=lambda w,idx=i: self._open(idx, pop))
            inner.add_widget(b)
        sv.add_widget(inner); box.add_widget(sv)
        pop.content = box; pop.open()

    def _open(self, idx, pop):
        self.cur = idx; self._save_convos(); pop.dismiss(); self._render_chat()

    def _render_chat(self):
        h = self.convos[self.cur]["history"]; lines=[]
        for m in h:
            if m["role"]=="user": lines.append("Ты:\n"+m["content"])
            elif m["role"]=="assistant": lines.append("Ассистент:\n"+m["content"])
        self.display.text = "\n\n".join(lines) if lines else "Новый диалог. Напиши сообщение."
        self._scroll_end()

    def _scroll_end(self):
        def _e(*a):
            try: self.display.cursor = (0, len(self.display._lines))
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
            self.display.text=self.ex_out; self._scroll_end()
            threading.Thread(target=self._do_price, args=(text,), daemon=True).start()
        elif self.mode == "тест":
            self.test_out += "\n\n> "+text+"\nдвойной тест на "+TREND_COIN+" и "+FLAT_COIN+", ~30-60 сек..."
            self.display.text=self.test_out; self._scroll_end()
            threading.Thread(target=self._do_test, args=(text,), daemon=True).start()
        else:
            if not self.ds_key:
                self.btn.disabled=False; self._popup_key("ds"); return
            self.convos[self.cur]["history"].append({"role":"user","content":text})
            self._render_chat()
            self.display.text += "\n\nАссистент: думаю..."; self._scroll_end()
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

    def _sym(self, coin): return coin.upper().replace("USDT","")+"USDT"

    def _do_price(self, coin):
        if bybit is None: self._res("ex","Биржа недоступна (pybit не загрузился)."); return
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
        self._res("ex", msg)

    def _do_test(self, text):
        strat = text.split()[0].lower() if text.split() else "тренд"
        if strat not in ("тренд","отбой","пробой"): self._res("test","Стратегии: тренд, отбой, пробой."); return
        try:
            r1,m1 = self._backtest(TREND_COIN, strat); r2,m2 = self._backtest(FLAT_COIN, strat)
            ev1,R1,t1=m1; ev2,R2,t2=m2
            ok1=(t1>=20 and R1>0 and ev1>=0.02); ok2=(t2>=20 and R2>0 and ev2>=0.02)
            v="\n=== СВОДКА ===\n"
            if ok1 and ok2: v+="'"+strat+"' работает И на тренде ("+TREND_COIN+"), И на боковике ("+FLAT_COIN+"). Крепко — проверь ещё на 2-3 монетах."
            elif ok1: v+="'"+strat+"' работает на трендовом "+TREND_COIN+", но НЕ на боковике "+FLAT_COIN+". Трендовая — годна только в тренде, на пиле сольёт."
            elif ok2: v+="Странно: прошла на "+FLAT_COIN+", но не на "+TREND_COIN+". Скорее случайность."
            else: v+="'"+strat+"' не прошла НИ на "+TREND_COIN+", НИ на "+FLAT_COIN+". Хлам."
            msg=r1+"\n"+r2+v
        except Exception as e:
            msg="Ошибка теста: "+str(e)[:80]
        self._res("test", msg)

    def _res(self, which, msg):
        def u(*a):
            if which=="ex":
                self.ex_out=self.ex_out.replace("...загружаю...","")+msg
                if self.mode=="биржа": self.display.text=self.ex_out
            else:
                base=self.test_out.split("двойной тест на")[0]
                self.test_out=base+msg
                if self.mode=="тест": self.display.text=self.test_out
            self._scroll_end(); self.btn.disabled=False
        Clock.schedule_once(u, 0)

    def _backtest(self, coin, strat):
        if bybit is None: return "Биржа недоступна.", (0,0,0)
        sym=self._sym(coin); col={}; end=None
        while len(col)<CANDLES:
            p=dict(category="spot",symbol=sym,interval=INTERVAL,limit=1000)
            if end is not None: p["end"]=end
            b=bybit.get_kline(**p)["result"]["list"]
            if not b: break
            for c in b: col[int(c[0])]=c
            ne=min(int(c[0]) for c in b)-1
            if end is not None and ne>=end: break
            end=ne
        cd=[col[t] for t in sorted(col)]
        H=[float(c[2]) for c in cd]; L=[float(c[3]) for c in cd]; C=[float(c[4]) for c in cd]; n=len(C)
        if n<200: return ("Мало данных по "+sym+" ("+str(n)+").", (0,0,0))
        TR=[H[0]-L[0]]
        for i in range(1,n): TR.append(max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])))
        ATR=[None]*n; ATR[ATR_LEN]=sum(TR[1:ATR_LEN+1])/ATR_LEN
        for i in range(ATR_LEN+1,n): ATR[i]=(ATR[i-1]*(ATR_LEN-1)+TR[i])/ATR_LEN
        sig=[]; trail=(strat!="пробой")
        for t in range(DON,n):
            hh=max(H[t-DON:t]); ll=min(L[t-DON:t]); a=ATR[t] or 0
            if a<=0: continue
            if strat=="отбой":
                if L[t]<ll: sig.append((t,"long",C[t],C[t]-2*a))
                elif H[t]>hh: sig.append((t,"short",C[t],C[t]+2*a))
            else:
                if H[t]>hh: sig.append((t,"long",hh,hh-2*a))
                elif L[t]<ll: sig.append((t,"short",ll,ll+2*a))
        def run(lo,hi):
            R=0.0; wins=0; tr=0
            for t,dirn,entry,stop0 in sig:
                if not (lo<=t<hi): continue
                risk=abs(entry-stop0)
                if risk<=0 or t+1>=n: continue
                stop=stop0; peak=entry; trough=entry; oc=None
                tgt=entry+2*risk if dirn=="long" else entry-2*risk
                for f in range(t+1,min(t+1+MAXH,n)):
                    a=ATR[f] or ATR[t] or risk
                    if dirn=="long":
                        if L[f]<=stop: oc=(stop-entry)/risk; break
                        if not trail and H[f]>=tgt: oc=2.0; break
                        peak=max(peak,H[f])
                        if trail: stop=max(stop,peak-MULT*a)
                    else:
                        if H[f]>=stop: oc=(entry-stop)/risk; break
                        if not trail and L[f]<=tgt: oc=2.0; break
                        trough=min(trough,L[f])
                        if trail: stop=min(stop,trough+MULT*a)
                if oc is None:
                    f=min(t+MAXH,n-1); oc=((C[f]-entry) if dirn=="long" else (entry-C[f]))/risk
                oc-=COST_RT*(entry/risk); tr+=1
                if oc>0: wins+=1
                R+=oc
            ev=R/tr if tr else 0; wr=wins/tr*100 if tr else 0
            return tr,wr,R,ev
        half=n//2
        o="Тест '"+strat+"' "+sym+" 4ч | свечей "+str(n)+" | сигналов "+str(len(sig))+"\n"
        for label,lo,hi in [("ВСЯ",0,n),("Обучение",0,half),("Проверка(OOS)",half,n)]:
            tr,wr,R,ev=run(lo,hi)
            o+=label+": сделок="+str(tr)+", винрейт="+str(round(wr,1))+"%, итог="+str(round(R,1))+"R, EV="+str(round(ev,3))+"R\n"
        ot,owr,oR,oev=run(half,n)
        return o, (oev, oR, ot)

if __name__ == "__main__":
    Assistant().run()
