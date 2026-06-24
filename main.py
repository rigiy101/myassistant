__version__ = "1.0"
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

class MyApp(App):
    def build(self):
        root = BoxLayout(orientation="vertical", padding=20, spacing=10)
        self.out = Label(text="Privet! Eto zagotovka assistenta.")
        self.inp = TextInput(hint_text="vvedi tekst", multiline=False,
                             size_hint_y=None, height=120)
        btn = Button(text="Nazhmi menya", size_hint_y=None, height=120)
        btn.bind(on_press=self.on_press)
        root.add_widget(self.out)
        root.add_widget(self.inp)
        root.add_widget(btn)
        return root

    def on_press(self, *a):
        self.out.text = "Ty napisal: " + self.inp.text

MyApp().run()
