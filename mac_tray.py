"""macOS: left click opens settings, right click retains the tray menu."""
import AppKit
import Foundation
import objc
import pystray


class QuickSwitchTrayDelegate(Foundation.NSObject):
    @objc.namedSelector(b"quickswitchClick:")
    def click_(self, sender):
        event = AppKit.NSApplication.sharedApplication().currentEvent()
        if event and event.type() == AppKit.NSRightMouseUp:
            if self.icon._menu_handle:
                self.icon._status_item.popUpStatusItemMenu_(self.icon._menu_handle[0])
        else:
            self.icon()  # Invokes the default settings action.


class MacTrayIcon(pystray.Icon):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._click_delegate = QuickSwitchTrayDelegate.alloc().init()
        self._click_delegate.icon = self
        button = self._status_item.button()
        button.setTarget_(self._click_delegate)
        button.setAction_(b"quickswitchClick:")
        button.sendActionOn_(AppKit.NSLeftMouseUpMask | AppKit.NSRightMouseUpMask)

    def _update_menu(self):
        super()._update_menu()
        # An attached NSMenu consumes clicks before the button action can run.
        self._status_item.setMenu_(None)
