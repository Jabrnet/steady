import pystray
from pystray import MenuItem as Item, Menu

from steady.core.filter import TremorFilter
from steady.tray.icon import make_icon

PROFILE_NAMES = list(TremorFilter.PREDEFINED_PROFILES.keys())


def build_tray(state, on_quit) -> pystray.Icon:
    """
    Build and return a pystray Icon (does not start it — call icon.run()).

    state   : SteadyState instance shared with InputHook
    on_quit : callable invoked before the tray icon stops
    """

    def toggle_enabled(icon, item):
        state.enabled = not state.enabled
        icon.icon = make_icon(state.enabled)
        icon.update_menu()

    def set_profile(name):
        def _set(icon, item):
            state.profile_name = name
            icon.update_menu()
        return _set

    def profile_checked(name):
        return lambda item: state.profile_name == name

    profile_items = [
        Item(
            name,
            set_profile(name),
            checked=profile_checked(name),
            radio=True,
        )
        for name in PROFILE_NAMES
    ]

    def quit_app(icon, item):
        on_quit()
        icon.stop()

    menu = Menu(
        Item(
            'Filtering: Enabled',
            toggle_enabled,
            checked=lambda item: state.enabled,
        ),
        Menu.SEPARATOR,
        Item('Profile', Menu(*profile_items)),
        Menu.SEPARATOR,
        Item('Quit', quit_app),
    )

    icon = pystray.Icon(
        name='steady',
        icon=make_icon(state.enabled),
        title='Steady - Tremor Filter',
        menu=menu,
    )
    return icon
