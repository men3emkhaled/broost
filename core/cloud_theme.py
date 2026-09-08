"""A complete light theme for native cashier widgets, independent of Windows."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette


def apply_cloud_theme(app):
    # Native Windows styles can ignore palette roles when Windows is dark.
    # Fusion and an explicit palette keep headers, dialogs and controls consistent.
    if app.style().objectName().lower() != 'fusion':
        app.setStyle('Fusion')
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = app.style().standardPalette()
    colors = {'Window':'#f5f6f8','WindowText':'#20252b','Base':'#ffffff',
              'AlternateBase':'#edf1f5','Text':'#20252b','Button':'#ffffff',
              'ButtonText':'#20252b','BrightText':'#ffffff','Highlight':'#176b46',
              'HighlightedText':'#ffffff','Accent':'#176b46','ToolTipBase':'#ffffff',
              'ToolTipText':'#20252b','PlaceholderText':'#596574',
              'Light':'#ffffff','Midlight':'#edf1f5','Mid':'#b8c2cc',
              'Dark':'#596574','Shadow':'#20252b','Link':'#135ca8','LinkVisited':'#68439b'}
    for name, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole,name),QColor(color))
    for role in (QPalette.ColorRole.WindowText,QPalette.ColorRole.Text,QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled,role,QColor('#66717f'))
    palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.Button,QColor('#e5e9ee'))
    app.setPalette(palette)
