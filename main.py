"""LORDZICO SMS Sender - free Android app. Sends bulk SMS from your own SIM credit. No internet needed."""
import base64
import io
import json
import math
import os
import re
import threading
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hexc, platform

import icons

ANDROID = platform == "android"
if ANDROID:
    from jnius import autoclass
    from android.permissions import Permission, check_permission, request_permissions

Window.softinput_mode = "resize"        # the screen shrinks above the keyboard instead of being covered

THEMES = {
    "dark": dict(bg="#0F1720", head="#0B5D3B", card="#18232F", field="#223140", text="#FFFFFF", muted="#9AA9B8", accent="#12A150", soft="#3A4B5C", softtext="#FFFFFF"),
    "dim": dict(bg="#1E2530", head="#2B6B57", card="#2A3340", field="#36404F", text="#E8EDF2", muted="#A5B0BD", accent="#2FAF7B", soft="#475365", softtext="#FFFFFF"),
    "light": dict(bg="#F2F5F8", head="#0B7A4B", card="#FFFFFF", field="#E8EEF4", text="#17202A", muted="#5C6B7A", accent="#12A150", soft="#D5DEE7", softtext="#17202A"),
    "blue": dict(bg="#0B1F3A", head="#1456A0", card="#12305A", field="#1B3F72", text="#FFFFFF", muted="#9CB6D8", accent="#1E88E5", soft="#2A5A9A", softtext="#FFFFFF"),
}
DANGER = hexc("#D64545")
T = {}


def use_theme(name):
    T.clear()
    T.update({k: hexc(v) for k, v in THEMES[name].items()})
    Window.clearcolor = T["bg"]


# ---------------- logic ----------------
def normalize(tok):
    """Return a clean phone number, or None if the text is not a number (names are skipped)."""
    if not re.fullmatch(r"\+?[\d\-\(\)\.]+", tok):
        return None
    plus = tok.startswith("+")
    d = re.sub(r"\D", "", tok)
    if len(d) == 9 and not plus:      # leading 0 lost (Excel), e.g. 241234567 -> 0241234567
        d = "0" + d
    return ("+" if plus else "") + d if 9 <= len(d) <= 15 else None


def parse_numbers(text):
    seen, out = set(), []
    for tok in re.split(r"[,\s;]+", text):
        n = normalize(tok) if tok else None
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def parts_of(m):
    single, multi = (70, 67) if any(ord(c) > 127 for c in m) else (160, 153)
    return 1 if len(m) <= single else math.ceil(len(m) / multi)


def send_sms(number, text):
    if not ANDROID:
        print("TEST (not on a phone):", number, text)
        return
    mgr = autoclass("android.telephony.SmsManager").getDefault()
    parts = mgr.divideMessage(text)
    if parts.size() > 1:
        mgr.sendMultipartTextMessage(number, None, parts, None, None)
    else:
        mgr.sendTextMessage(number, None, text, None, None)


def load_settings(folder):
    try:
        with open(os.path.join(folder, "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(folder, st):
    try:
        with open(os.path.join(folder, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception:
        pass


# ---------------- design helpers ----------------
_cache = {}


def ic(name):
    if name not in _cache:
        _cache[name] = CoreImage(io.BytesIO(base64.b64decode(icons.ICONS[name])), ext="png").texture
    return _cache[name]


def icon_img(name, size=22):
    return Image(texture=ic(name), size_hint=(None, None), size=(dp(size), dp(size)), pos_hint={"center_y": 0.5})


def lab(text="", size=14, color=None, bold=False, halign="left", markup=False, **kw):
    l = Label(text=text, font_size=sp(size), color=color or T["text"], bold=bold, halign=halign,
              valign="middle", markup=markup, size_hint_y=None, **kw)
    l.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
    l.bind(texture_size=lambda i, s: setattr(i, "height", s[1] + dp(6)))
    return l


def tinput(**kw):
    return TextInput(background_normal="", background_active="", background_color=T["field"],
                     foreground_color=T["text"], hint_text_color=T["muted"], cursor_color=T["accent"],
                     padding=[dp(12), dp(10)], font_size=sp(16), size_hint_y=None, write_tab=False, **kw)


class Card(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_y=None, **kw)
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*T["card"])
            self._bg = RoundedRectangle(radius=[dp(14)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._bg.pos, self._bg.size = self.pos, self.size


class Btn(ButtonBehavior, BoxLayout):
    def __init__(self, text, icon=None, color=None, tcolor=(1, 1, 1, 1), height=48, **kw):
        super().__init__(size_hint_y=None, height=dp(height), spacing=dp(8), **kw)
        self.col = color or T["accent"]
        with self.canvas.before:
            self._c = Color(*self.col)
            self._r = RoundedRectangle(radius=[dp(12)])
        self.bind(pos=self._sync, size=self._sync, state=self._tint, disabled=self._tint)
        self.add_widget(Widget())
        if icon:
            self.add_widget(icon_img(icon))
        self.lbl = Label(text=text, bold=True, size_hint_x=None, font_size=sp(15), color=tcolor)
        self.lbl.bind(texture_size=lambda i, s: setattr(i, "width", s[0] + dp(6)))
        self.add_widget(self.lbl)
        self.add_widget(Widget())

    def _sync(self, *a):
        self._r.pos, self._r.size = self.pos, self.size

    def _tint(self, *a):
        r, g, b, al = self.col
        f = 0.45 if self.disabled else (0.75 if self.state == "down" else 1)
        self._c.rgba = (r * f, g * f, b * f, al)


def ask_text(title, hint, text, on_ok):
    box = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12))
    inp = tinput(height=dp(46), multiline=False, text=text, hint_text=hint)
    box.add_widget(inp)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    ok, cancel = Btn("Save"), Btn("Cancel", color=T["soft"], tcolor=T["softtext"])
    row.add_widget(ok)
    row.add_widget(cancel)
    box.add_widget(row)
    pop = Popup(title=title, content=box, size_hint=(0.9, None), height=dp(220))
    cancel.bind(on_release=pop.dismiss)
    ok.bind(on_release=lambda *_: (pop.dismiss(), on_ok(inp.text.strip())))
    pop.open()


def confirm(title, text, on_yes):
    box = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12))
    box.add_widget(Label(text=text, halign="center"))
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    yes, no = Btn("Yes"), Btn("No", color=T["soft"], tcolor=T["softtext"])
    row.add_widget(yes)
    row.add_widget(no)
    box.add_widget(row)
    pop = Popup(title=title, content=box, size_hint=(0.9, None), height=dp(220))
    no.bind(on_release=pop.dismiss)
    yes.bind(on_release=lambda *_: (pop.dismiss(), on_yes()))
    pop.open()


def spinner(text, values, **kw):
    return Spinner(text=text, values=values, background_normal="", background_color=T["field"],
                   color=T["text"], font_size=sp(15), **kw)


# ---------------- screen ----------------
class Root(BoxLayout):
    def __init__(self, st, **kw):
        super().__init__(orientation="vertical", **kw)
        self.stop = False
        self.st = st
        st.setdefault("groups", {})
        st.setdefault("signs", [])
        self.cur_group = None
        self.add_widget(self.header())
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        body = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        self.scroll.add_widget(body)
        self.add_widget(self.scroll)

        # message card
        c = Card()
        c.add_widget(self.title("Message", "chat"))
        self.msg = tinput(height=dp(120), text=st.get("msg", ""), hint_text="Type your message here")
        self.sign = tinput(height=dp(46), multiline=False, text=st.get("sign", ""),
                           hint_text="Your business name (added at the end)")
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        self.nsp = spinner("Saved names", list(st["signs"]), size_hint_x=0.6)
        self.nsp.bind(text=self.pick_name)
        bn = Btn("Save name", color=T["soft"], tcolor=T["softtext"], height=46, size_hint_x=0.4)
        bn.bind(on_release=self.save_name)
        row.add_widget(self.nsp)
        row.add_widget(bn)
        self.chars = lab("", 12, T["muted"])
        for w in (self.msg, self.sign, row, self.chars):
            c.add_widget(w)
        body.add_widget(c)

        # recipients card
        c = Card()
        self.cnt = lab("0 numbers", 13, T["accent"], bold=True, halign="right", size_hint_x=None, width=dp(130), pos_hint={"center_y": 0.5})
        c.add_widget(self.title("Recipients", "people", self.cnt))
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        self.gsp = spinner("Saved groups", sorted(st["groups"]), size_hint_x=0.5)
        self.gsp.bind(text=self.load_group)
        bs = Btn("Save", color=T["soft"], tcolor=T["softtext"], height=46, size_hint_x=0.25)
        bd = Btn("Delete", color=T["soft"], tcolor=T["softtext"], height=46, size_hint_x=0.25)
        bs.bind(on_release=self.save_group)
        bd.bind(on_release=self.delete_group)
        for w in (self.gsp, bs, bd):
            row.add_widget(w)
        c.add_widget(row)
        self.numbers = tinput(height=dp(120), text=st.get("numbers", ""), hint_text="Paste numbers (commas, spaces or new lines)")
        c.add_widget(self.numbers)
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        b1 = Btn("Load file", "file", T["soft"], T["softtext"], 46)
        b2 = Btn("Clear", "clear", T["soft"], T["softtext"], 46)
        b1.bind(on_release=self.pick)
        b2.bind(on_release=lambda *_: setattr(self.numbers, "text", ""))
        row.add_widget(b1)
        row.add_widget(b2)
        c.add_widget(row)
        body.add_widget(c)

        # options card
        c = Card()
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        self.avail = tinput(height=dp(46), multiline=False, input_filter="int", text=st.get("avail", ""), hint_text="SMS I have (optional)")
        self.delay = tinput(height=dp(46), multiline=False, input_filter="float", text=st.get("delay", "3"), hint_text="Seconds between")
        row.add_widget(self.avail)
        row.add_widget(self.delay)
        c.add_widget(row)
        self.info = lab("", 13, T["muted"], halign="center")
        c.add_widget(self.info)
        body.add_widget(c)

        # actions
        row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        self.go = Btn("SEND", "send", T["accent"], height=56, size_hint_x=0.65)
        stop = Btn("STOP", "stop", DANGER, height=56, size_hint_x=0.35)
        self.go.bind(on_release=self.start)
        stop.bind(on_release=lambda *_: setattr(self, "stop", True))
        row.add_widget(self.go)
        row.add_widget(stop)
        body.add_widget(row)

        c = Card()
        self.status = lab("Free app. Messages are paid from your own SMS credit. No internet needed.", 13, T["muted"], halign="center")
        c.add_widget(self.status)
        body.add_widget(c)

        # footer: brand + theme
        c = Card()
        brand = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
        brand.add_widget(Image(texture=ic("logo"), size_hint=(None, None), size=(dp(34), dp(34)), pos_hint={"center_y": 0.5}))
        brand.add_widget(lab("Powered by [b]LORDZICO[/b]", 14, markup=True, pos_hint={"center_y": 0.5}))
        c.add_widget(brand)
        c.add_widget(lab("Choose your colour", 12, T["muted"]))
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        for key, name in (("dark", "Dark"), ("dim", "Dim"), ("light", "Light"), ("blue", "Blue")):
            b = Btn(name, color=hexc(THEMES[key]["head"]), height=40)
            b.bind(on_release=lambda *_, k=key: App.get_running_app().set_theme(k))
            row.add_widget(b)
        c.add_widget(row)
        body.add_widget(c)

        for w in (self.msg, self.sign, self.numbers, self.avail, self.delay):
            w.bind(focus=self.focused)
        self.numbers.bind(text=self.refresh)
        self.msg.bind(text=self.refresh)
        self.sign.bind(text=self.refresh)
        self.refresh()
        if ANDROID:
            request_permissions([Permission.SEND_SMS])

    def header(self):
        h = BoxLayout(size_hint_y=None, height=dp(70), padding=[dp(14), dp(8)], spacing=dp(12))
        with h.canvas.before:
            Color(*T["head"])
            bg = Rectangle()
        h.bind(pos=lambda i, v: setattr(bg, "pos", v), size=lambda i, v: setattr(bg, "size", v))
        h.add_widget(Image(texture=ic("logo"), size_hint=(None, None), size=(dp(48), dp(48)), pos_hint={"center_y": 0.5}))
        t = Label(text="[b]LORDZICO[/b]\n[size=13sp]SMS Sender  |  free  |  no internet needed[/size]", markup=True,
                  halign="left", valign="middle", font_size=sp(21), color=(1, 1, 1, 1))
        t.bind(size=lambda i, s: setattr(i, "text_size", s))
        h.add_widget(t)
        return h

    def title(self, text, icon, right=None):
        row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
        row.add_widget(icon_img(icon))
        row.add_widget(lab(text, 16, bold=True, pos_hint={"center_y": 0.5}))
        if right:
            row.add_widget(right)
        return row

    def focused(self, widget, value):
        if value:       # after the keyboard opens, scroll so the box you are typing in stays visible
            Clock.schedule_once(lambda dt: self.scroll.scroll_to(widget, padding=dp(30), animate=True), 0.4)

    def values(self):
        return dict(numbers=self.numbers.text, msg=self.msg.text, sign=self.sign.text, avail=self.avail.text, delay=self.delay.text)

    def full_message(self):
        m, s = self.msg.text.strip(), self.sign.text.strip()
        return (m + "\n" + s) if (m and s) else m

    def say(self, t):
        Clock.schedule_once(lambda dt: setattr(self.status, "text", t))

    def refresh(self, *_):
        n, m = len(parse_numbers(self.numbers.text)), self.full_message()
        p = parts_of(m) if m else 0
        self.cnt.text = f"{n} number{'s' if n != 1 else ''}"
        self.chars.text = f"{len(m)} characters  |  {p} SMS each"
        self.info.text = f"{n * p} SMS will be used from your own credit"

    # ---- saved groups and business names ----
    def load_group(self, spin, text):
        if text == "Saved groups":
            return
        nums = self.st["groups"].get(text, [])
        self.numbers.text = "\n".join(nums)
        self.cur_group = text
        spin.text = "Saved groups"
        self.say(f'Group "{text}" loaded: {len(nums)} numbers')

    def save_group(self, *_):
        nums = parse_numbers(self.numbers.text)
        if not nums:
            return self.say("Add some numbers first, then tap Save to keep them as a group.")

        def done(name):
            if name:
                self.st["groups"][name] = nums
                self.cur_group = name
                self.gsp.values = sorted(self.st["groups"])
                App.get_running_app().save()
                self.say(f'Group "{name}" saved with {len(nums)} numbers.')
        ask_text("Save group", "Group name, e.g. Church members", self.cur_group or "", done)

    def delete_group(self, *_):
        g = self.cur_group
        if not g or g not in self.st["groups"]:
            return self.say("Load a group first, then tap Delete.")

        def yes():
            self.st["groups"].pop(g, None)
            self.cur_group = None
            self.gsp.values = sorted(self.st["groups"])
            App.get_running_app().save()
            self.say(f'Group "{g}" deleted.')
        confirm("Delete group", f'Delete the group "{g}"?', yes)

    def pick_name(self, spin, text):
        if text != "Saved names":
            self.sign.text = text
            spin.text = "Saved names"

    def save_name(self, *_):
        n = self.sign.text.strip()
        if not n:
            return self.say("Type your business name first, then tap Save name.")
        if n not in self.st["signs"]:
            self.st["signs"].append(n)
        self.nsp.values = list(self.st["signs"])
        App.get_running_app().save()
        self.say(f'Business name "{n}" saved.')

    def pick(self, *_):
        try:
            from plyer import filechooser
            filechooser.open_file(on_selection=lambda s: Clock.schedule_once(lambda dt: self.loaded(s)), filters=["*.csv", "*.txt"])
        except Exception:
            self.say("File picker not available. Please paste the numbers instead.")

    def loaded(self, sel):
        if not sel:
            return
        try:
            with open(sel[0], encoding="utf-8-sig", errors="ignore") as f:
                self.numbers.text = (self.numbers.text + "\n" + f.read()).strip()
        except Exception:
            self.say("Could not read that file. Please paste the numbers instead.")

    def start(self, *_):
        nums, msg = parse_numbers(self.numbers.text), self.full_message()
        if not nums or not msg:
            return self.say("Add numbers and type a message first.")
        if ANDROID and not check_permission(Permission.SEND_SMS):
            request_permissions([Permission.SEND_SMS])
            return self.say("Tap ALLOW for SMS permission, then press SEND again.")
        p = parts_of(msg)
        if self.avail.text.strip() and int(self.avail.text) // p < len(nums):
            nums = nums[: int(self.avail.text) // p]
            if not nums:
                return self.say("You do not have enough SMS for even one number.")
        try:
            delay = max(1.0, float(self.delay.text or 3))
        except ValueError:
            delay = 3.0
        box = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12))
        box.add_widget(Label(text=f"Send to {len(nums)} numbers?\nThis uses about {len(nums) * p} SMS from your own credit.", halign="center"))
        yn = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        yes, no = Btn("Yes, send", "send"), Btn("Cancel", color=T["soft"], tcolor=T["softtext"])
        yn.add_widget(yes)
        yn.add_widget(no)
        box.add_widget(yn)
        pop = Popup(title="Confirm", content=box, size_hint=(0.9, None), height=dp(230))
        no.bind(on_release=pop.dismiss)
        yes.bind(on_release=lambda *_: (pop.dismiss(), self.begin(nums, msg, delay)))
        pop.open()

    def begin(self, nums, msg, delay):
        App.get_running_app().save()
        self.stop = False
        self.go.disabled = True
        threading.Thread(target=self.run, args=(nums, msg, delay), daemon=True).start()

    def run(self, nums, msg, delay):
        sent = failed = 0
        for n in nums:
            if self.stop:
                break
            try:
                send_sms(n, msg)
                sent += 1
            except Exception:
                failed += 1
            self.say(f"Handed to phone: {sent} of {len(nums)}  |  errors {failed}")
            time.sleep(delay)
        self.say(f"Finished. {sent} sent to your phone's SMS system, {failed} errors." + (" (stopped)" if self.stop else ""))
        Clock.schedule_once(lambda dt: setattr(self.go, "disabled", False))


class SMSApp(App):
    title = "LORDZICO SMS Sender"
    icon = "icon.png"

    def build(self):
        self.st = load_settings(self.user_data_dir)
        use_theme(self.st.get("theme", "dark"))
        self.holder = BoxLayout()
        self.holder.add_widget(Root(self.st))
        return self.holder

    def save(self):
        if self.holder.children:
            self.st.update(self.holder.children[0].values())
        save_settings(self.user_data_dir, self.st)

    def set_theme(self, name):
        self.save()
        self.st["theme"] = name
        save_settings(self.user_data_dir, self.st)
        use_theme(name)
        self.holder.clear_widgets()
        self.holder.add_widget(Root(self.st))

    def on_pause(self):
        self.save()
        return True

    def on_stop(self):
        self.save()


if __name__ == "__main__":
    SMSApp().run()
