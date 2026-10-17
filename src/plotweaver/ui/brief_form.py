"""Book brief fields on the new-book screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from plotweaver.brief import BookBrief, Character, compile_brief
from plotweaver.length import STRUCTURAL_MAX_PAGES, plan_shape
from plotweaver.ui.i18n import tr
from plotweaver.ui.presets import MAX_SCENES_PER_CHAPTER

_POV = (
    ("pov_third", "third-person limited"),
    ("pov_first", "first person"),
    ("pov_omniscient", "third-person omniscient"),
)
_TENSE = (("tense_past", "past"), ("tense_present", "present"))
_AUDIENCE = (
    ("audience_adult", "adult"),
    ("audience_teen", "teen"),
    ("audience_child", "child"),
)


class BriefForm:
    """The brief controls. The window still owns title, language, synopsis, and dark themes."""

    def __init__(self, parent: QWidget) -> None:
        self._parent = parent
        self._title: QLineEdit | None = None
        self._language: QComboBox | None = None
        self._synopsis: QPlainTextEdit | None = None
        self._dark: QCheckBox | None = None
        self._chapters: QSpinBox | None = None
        self._guessed: list[str] = []
        self._marks: dict[str, QLabel] = {}
        self._loading = False
        self._edited = False
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(tr("brief_notes_hint"))
        self.notes.setMinimumHeight(80)
        self.help_button = QPushButton(tr("brief_help"))
        self.help_button.setObjectName("briefHelp")
        self.copy_button = QPushButton(tr("brief_copy"))
        self.copy_button.setObjectName("briefCopy")
        self.paste_button = QPushButton(tr("brief_paste"))
        self.paste_button.setObjectName("briefPaste")
        self.pages = QSpinBox()
        self.pages.setRange(1, STRUCTURAL_MAX_PAGES)
        self.pages.setValue(250)
        self.words_per_page = QSpinBox()
        self.words_per_page.setRange(100, 600)
        self.words_per_page.setValue(250)
        self.target_label = QLabel("80000")
        self.chapter_hint = QLabel("")
        self.chapter_hint.setObjectName("muted")
        self.scenes = QSpinBox()
        self.scenes.setRange(1, MAX_SCENES_PER_CHAPTER)
        self.scenes.setValue(2)
        self.genre = QLineEdit()
        self.subgenre = QLineEdit()
        self.tone = QLineEdit()
        self.pov = QComboBox()
        self.pov.setEditable(True)
        self.pov.setObjectName("pov")
        for key, value in _POV:
            self.pov.addItem(tr(key), value)
        self.tense = QComboBox()
        self.tense.setEditable(True)
        self.tense.setObjectName("tense")
        for key, value in _TENSE:
            self.tense.addItem(tr(key), value)
        self.audience = QComboBox()
        self.audience.setEditable(True)
        for key, value in _AUDIENCE:
            self.audience.addItem(tr(key), value)
        self.setting = QLineEdit()
        self.characters = QTableWidget(0, 4)
        self.characters.setHorizontalHeaderLabels(
            [tr("char_name"), tr("char_role"), tr("char_description"), tr("char_gender")]
        )
        header = self.characters.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.characters.setMinimumHeight(120)
        self.add_character = QPushButton(tr("add_character"))
        self.add_character.clicked.connect(self._add_row)
        self.plot_points = QPlainTextEdit()
        self.plot_points.setPlaceholderText(tr("one_per_line"))
        self.plot_points.setMinimumHeight(70)
        self.ending = QComboBox()
        self.ending.setEditable(True)
        for value in ("closed", "open", "bittersweet", "twist", "tragic"):
            self.ending.addItem(value, value)
        self.style_references = QPlainTextEdit()
        self.style_references.setPlaceholderText(tr("one_per_line"))
        self.style_references.setMinimumHeight(50)
        self.preview_toggle = QToolButton()
        self.preview_toggle.setText(tr("prompt_preview"))
        self.preview_toggle.setCheckable(True)
        self.preview_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.preview_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.preview_toggle.setObjectName("promptPreview")
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("promptPreviewText")
        self.preview.setVisible(False)
        self.preview.setMinimumHeight(140)
        self.preview_toggle.toggled.connect(self._toggle_preview)
        self.preview.textChanged.connect(self._preview_edited)
        self.pages.valueChanged.connect(self._refresh_numbers)
        self.words_per_page.valueChanged.connect(self._refresh_numbers)
        self._refresh_numbers()

    def bind(
        self,
        title: QLineEdit,
        language: QComboBox,
        synopsis: QPlainTextEdit,
        dark: QCheckBox,
        chapters: QSpinBox,
    ) -> None:
        """Watch the fields the rest of the form already owns."""
        self._title = title
        self._language = language
        self._synopsis = synopsis
        self._dark = dark
        self._chapters = chapters
        self._watch_text(title, "title")
        self._watch_text(synopsis, "synopsis")
        language.currentIndexChanged.connect(lambda _index: self._clear_guess("language"))
        dark.toggled.connect(lambda _checked: self._clear_guess("dark_themes"))
        chapters.valueChanged.connect(lambda _value: self._clear_guess("chapter_count"))
        self._watch_text(self.notes, "notes")
        self._watch_text(self.genre, "genre")
        self._watch_text(self.subgenre, "subgenre")
        self._watch_text(self.tone, "tone")
        self._watch_text(self.setting, "setting")
        self._watch_text(self.plot_points, "plot_points")
        self._watch_text(self.style_references, "style_references")
        self.pov.currentTextChanged.connect(lambda _text: self._clear_guess("pov"))
        self.tense.currentTextChanged.connect(lambda _text: self._clear_guess("tense"))
        self.audience.currentTextChanged.connect(lambda _text: self._clear_guess("audience"))
        self.ending.currentTextChanged.connect(lambda _text: self._clear_guess("ending_type"))
        self.pages.valueChanged.connect(lambda _value: self._clear_guess("pages"))
        self.words_per_page.valueChanged.connect(lambda _value: self._clear_guess("words_per_page"))
        self.scenes.valueChanged.connect(lambda _value: self._clear_guess("scenes_per_chapter"))
        self.characters.itemChanged.connect(lambda _item: self._clear_guess("characters"))

    def populate(self, form: QFormLayout) -> None:
        """Add the brief rows to the new-book form."""
        form.addRow(tr("brief_notes"), self.notes)
        buttons = QHBoxLayout()
        buttons.addWidget(self.help_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.paste_button)
        form.addRow("", buttons)
        form.addRow(tr("pages"), self._marked("pages", self.pages))
        form.addRow(tr("words_per_page"), self._marked("words_per_page", self.words_per_page))
        form.addRow(tr("target_words"), self.target_label)
        form.addRow("", self.chapter_hint)
        form.addRow(tr("scenes"), self._marked("scenes_per_chapter", self.scenes))
        form.addRow(tr("genre"), self._marked("genre", self.genre))
        form.addRow(tr("subgenre"), self._marked("subgenre", self.subgenre))
        form.addRow(tr("tone"), self._marked("tone", self.tone))
        form.addRow(tr("pov"), self._marked("pov", self.pov))
        form.addRow(tr("tense"), self._marked("tense", self.tense))
        form.addRow(tr("audience"), self._marked("audience", self.audience))
        form.addRow(tr("setting"), self._marked("setting", self.setting))
        character_box = QVBoxLayout()
        character_box.addWidget(self.characters)
        character_box.addWidget(self.add_character)
        form.addRow(tr("characters"), self._marked("characters", character_box))
        form.addRow(tr("plot_points"), self._marked("plot_points", self.plot_points))
        form.addRow(tr("ending"), self._marked("ending_type", self.ending))
        form.addRow(tr("style_references"), self._marked("style_references", self.style_references))
        form.addRow("", self.preview_toggle)
        form.addRow("", self.preview)

    def apply(self, brief: BookBrief) -> None:
        """Fill the controls and mark every field the model had to guess."""
        self._loading = True
        self.pages.setValue(brief.pages)
        self.words_per_page.setValue(brief.words_per_page)
        self.scenes.setValue(brief.derived_scenes())
        self.genre.setText(brief.genre)
        self.subgenre.setText(brief.subgenre)
        self.tone.setText(brief.tone)
        self._set_combo(self.pov, brief.pov)
        self._set_combo(self.tense, brief.tense)
        self._set_combo(self.audience, brief.audience)
        self.setting.setText(brief.setting)
        self._set_combo(self.ending, brief.ending_type)
        self.plot_points.setPlainText("\n".join(brief.plot_points))
        self.style_references.setPlainText("\n".join(brief.style_references))
        self.characters.setRowCount(0)
        for person in brief.characters:
            self._add_row()
            row = self.characters.rowCount() - 1
            values = (person.name, person.role, person.description, person.gender)
            for column, value in enumerate(values):
                self.characters.setItem(row, column, QTableWidgetItem(value))
        self._guessed = list(brief.guessed)
        for key, mark in self._marks.items():
            mark.setVisible(key in self._guessed)
        self._edited = False
        self._loading = False
        self._refresh_numbers()
        self.refresh_preview()

    def read_lenient(self) -> BookBrief:
        """Current form values. Empty text stays empty so the preview can still render."""
        assert self._title is not None
        assert self._language is not None
        assert self._synopsis is not None
        assert self._dark is not None
        assert self._chapters is not None
        chapters = self._chapters.value()
        return BookBrief(
            title=self._title.text().strip(),
            language=str(self._language.currentData() or "en"),
            pages=self.pages.value(),
            words_per_page=self.words_per_page.value(),
            genre=self.genre.text().strip(),
            subgenre=self.subgenre.text().strip(),
            tone=self.tone.text().strip(),
            pov=self._combo_value(self.pov) or "third-person limited",
            tense=self._combo_value(self.tense) or "past",
            audience=self._combo_value(self.audience),
            setting=self.setting.text().strip(),
            characters=self._people(),
            plot_points=self._lines(self.plot_points),
            ending_type=self._combo_value(self.ending),
            style_references=self._lines(self.style_references),
            dark_themes=self._dark.isChecked(),
            synopsis=self._synopsis.toPlainText().strip(),
            guessed=list(self._guessed),
            chapter_count=None if chapters == 0 else chapters,
            scenes_per_chapter=self.scenes.value(),
        )

    def override_text(self) -> str:
        """The preview text when the user changed it, otherwise empty."""
        if not self._edited:
            return ""
        return self.preview.toPlainText().strip()

    def refresh_preview(self) -> None:
        """Rebuild the preview until the user edits it."""
        if self._edited or self._title is None:
            return
        self._loading = True
        self.preview.setPlainText(compile_brief(self.read_lenient()))
        self._loading = False

    def _marked(self, key: str, widget: QWidget | QVBoxLayout) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        if isinstance(widget, QVBoxLayout):
            row.addLayout(widget, 1)
        else:
            row.addWidget(widget, 1)
        mark = QLabel(tr("guessed"))
        mark.setObjectName("faint")
        mark.setVisible(False)
        self._marks[key] = mark
        row.addWidget(mark)
        return host

    def _add_row(self) -> None:
        self.characters.insertRow(self.characters.rowCount())

    def _people(self) -> list[Character]:
        people: list[Character] = []
        for row in range(self.characters.rowCount()):
            name = self._cell(row, 0)
            if not name:
                continue
            gender = self._cell(row, 3).lower() or "unspecified"
            if gender not in {"male", "female", "unspecified"}:
                gender = "unspecified"
            people.append(Character(name, self._cell(row, 1), self._cell(row, 2), gender))
        return people

    def _cell(self, row: int, column: int) -> str:
        item = self.characters.item(row, column)
        if item is None:
            return ""
        return item.text().strip()

    def _lines(self, editor: QPlainTextEdit) -> list[str]:
        return [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]

    def _combo_value(self, box: QComboBox) -> str:
        data = box.currentData()
        if isinstance(data, str) and box.currentText() == box.itemText(box.currentIndex()):
            return data
        return box.currentText().strip()

    def _set_combo(self, box: QComboBox, value: str) -> None:
        index = box.findData(value)
        if index < 0:
            index = box.findText(value)
        if index >= 0:
            box.setCurrentIndex(index)
            return
        box.setEditText(value)

    def _toggle_preview(self, open_preview: bool) -> None:
        self.preview.setVisible(open_preview)
        arrow = Qt.ArrowType.DownArrow if open_preview else Qt.ArrowType.RightArrow
        self.preview_toggle.setArrowType(arrow)
        if open_preview:
            self.refresh_preview()

    def _preview_edited(self) -> None:
        if not self._loading:
            self._edited = True

    def _clear_guess(self, key: str) -> None:
        if self._loading:
            return
        if key in self._guessed:
            self._guessed = [item for item in self._guessed if item != key]
        mark = self._marks.get(key)
        if mark is not None:
            mark.setVisible(False)
        self._refresh_numbers()
        self.refresh_preview()

    def _watch_text(self, widget: QLineEdit | QPlainTextEdit, key: str) -> None:
        widget.textChanged.connect(lambda: self._clear_guess(key))

    def _book_language(self) -> str:
        combo = self._language
        if combo is None:
            return "ru"
        data = combo.currentData()
        if isinstance(data, str) and data:
            return data
        return "ru"

    def _refresh_numbers(self) -> None:
        words = self.pages.value() * self.words_per_page.value()
        self.target_label.setText(str(words))
        chapters, scenes, _per_scene = plan_shape(max(1, words), self._book_language(), None, None)
        self.chapter_hint.setText(tr("chapters_auto").format(count=chapters, scenes=scenes))
