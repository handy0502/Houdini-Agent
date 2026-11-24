"""Exercise the real QML shell offline in its own QApplication process."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtQuickWidgets")


def test_qml_navigation_composer_and_appearance(tmp_path):
    code = textwrap.dedent(r"""
        import json, os, sys
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        hfs = Path(os.environ.get('HFS', ''))
        if os.name == 'nt' and hfs.is_absolute() and (hfs / 'bin').is_dir():
            dll_handle = os.add_dll_directory(str(hfs / 'bin'))
        from PySide6.QtCore import QObject, QPointF, QSettings, Qt, QMetaObject, qInstallMessageHandler
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from PySide6.QtQuickWidgets import QQuickWidget
        from PySide6.QtQml import QQmlExpression, qmlContext
        app = QApplication([])
        from houdini_agent.ui_qml import controller as module
        from houdini_agent.ui_qml.host import create_view
        state = Path(sys.argv[1])
        settings = QSettings(str(state / 'prefs.ini'), QSettings.IniFormat)
        for key, value in [('app_theme', 'noir'), ('accent_key', 'warm'), ('font_family_key', 'editorial')]:
            settings.setValue(key, value)
        warnings = []
        def message_handler(kind, context, message):
            if any(word in message for word in ['ReferenceError', 'TypeError', 'Cannot assign', 'Unable to assign', 'Binding loop']):
                warnings.append(message)
        qInstallMessageHandler(message_handler)
        with patch.object(module, 'QSettings', return_value=settings), \
             patch.object(module.Controller, '_session_cache_dir', return_value=state/'sessions'), \
             patch.object(module.Controller, '_migrate_legacy_sessions'), \
             patch.object(module.Controller, '_auto_refresh_models_if_stale'), \
             patch('shared.common_utils.get_repo_root', return_value=str(state)), \
             patch('houdini_agent.meshy.telemetry.start'):
            model = module.ChatModel()
            controller = module.Controller(model, use_backend=False)
            assert (controller.appTheme, controller.accentKey, controller.fontFamilyKey) == ('graphite', 'neutral', 'modern')
            # A later explicit appearance choice is retained, including editorial.
            settings.setValue('font_family_key', 'editorial')
            controller._load_prefs()
            assert controller.fontFamilyKey == 'editorial'
            controller.setFontFamilyKey('modern')
            view = create_view(controller=controller, model=model)
            view.resize(1180, 820)
            assert view.quickWindow().color() == view.rootObject().property('color')
            view.show()
            QTest.qWait(100)
            assert view.status() != QQuickWidget.Error, [e.toString() for e in view.errors()]
            root = view.rootObject()
            def visual_find(item, name):
                if item.objectName() == name:
                    return item
                for child in item.childItems():
                    found = visual_find(child, name)
                    if found is not None:
                        return found
                return None
            def find(name, parent=root):
                item = parent.findChild(QObject, name)
                if item is None:
                    item = visual_find(view.quickWindow().contentItem(), name)
                assert item is not None, 'Missing QML object: ' + name
                return item
            def click(item):
                pos = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
                QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, pos)
                QTest.qWait(60)
            def open_settings():
                settings_button = find('settingsButton')
                if settings_button.isVisible():
                    click(settings_button)
                else:
                    QTest.keyClick(view, Qt.Key_Comma, Qt.ControlModifier)
                    QTest.qWait(60)
            def drag_sidebar(delta):
                handle = find('sidebarResizeHandle')
                start = handle.mapToScene(QPointF(handle.width()/2, handle.height()/2))
                QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, start.toPoint())
                for step in range(1, 13):
                    QTest.mouseMove(view, (start + QPointF(delta * step/12, 0)).toPoint())
                    QTest.qWait(8)
                QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, (start + QPointF(delta, 0)).toPoint())
                QTest.qWait(60)
            assert root.property('wide')
            settings_gear = find('settingsButton')
            assert settings_gear.property('icon') == 'gear'
            gear_point = settings_gear.mapToScene(QPointF(0, 0))
            assert gear_point.x() < find('dockedSidebar').width()
            assert gear_point.y() > view.height() - settings_gear.height() * 2
            # Startup stays in chat. One compact header menu owns discovering,
            # connecting to, switching, and launching Houdini sessions.
            from houdini_agent.ui_qml import external_app as external
            from houdini_agent.bridge import doctor
            installs = [dict(version='22.0.429', path='C:/fake/22', exe='fake22'),
                        dict(version='21.0.631', path='C:/fake/21', exe='fake21')]
            discovered = [dict(port=45173, version='22.0.429'), dict(port=45174, version='21.0.631')]
            coordinator = external.ExternalCoordinator(view, controller, str(state))
            coordinator.poll = MagicMock()
            with patch.object(external, 'find_houdini_installs', return_value=installs), \
                 patch.object(coordinator, '_ensure_packages'), \
                 patch.object(coordinator, '_start_session_build'), \
                 patch.object(coordinator, '_poll_tick') as probe, \
                 patch.object(controller, 'refreshContext'), \
                 patch.object(external, 'launch_houdini') as launch, \
                 patch.object(doctor, 'discover_sessions', return_value=discovered), \
                 patch.dict(os.environ, {'HAGENT_BRIDGE_PORT': '45172'}):
                controller.requestHoudiniAction.connect(coordinator.connection_action)
                coordinator.start()
                connection = find('houdiniConnectionButton')
                menu = find('houdiniConnectionMenu')
                assert not menu.property('visible')
                launch.assert_not_called()
                coordinator._on_poll_result(None)
                assert controller.houdiniConnection['state'] == 'disconnected'
                assert find('houdiniStatusDot').property('color') == find('houdiniStatusLabel').property('color')
                assert find('houdiniStatusDot').property('color').name() == '#ff4d4f'
                click(connection)
                import time
                deadline = time.monotonic() + 3
                while controller.houdiniConnection['busy'] and time.monotonic() < deadline:
                    time.sleep(0.01)
                    QTest.qWait(20)
                assert menu.property('visible') and not controller.houdiniConnection['busy']
                assert controller.houdiniConnection['sessions'] == discovered
                def assert_menu_anchor():
                    anchor = connection.mapToScene(QPointF(connection.width(), connection.height()))
                    assert abs(menu.property('x') + menu.property('width') - anchor.x()) < 1.1
                    assert anchor.y() <= menu.property('y') <= anchor.y() + 12
                    assert menu.property('height') <= view.height() / 3 + 1
                assert_menu_anchor()
                scrollbar = find('houdiniMenuScrollBar')
                assert not scrollbar.property('visible')
                view.resize(960, 820)
                QTest.qWait(80)
                assert_menu_anchor()
                controller.update_houdini_connection(sessions=[dict(port=46000 + i, version='22.0.test') for i in range(18)])
                QTest.qWait(80)
                assert scrollbar.property('visible')
                assert_menu_anchor()
                scroll_view = find('houdiniMenuScrollView')
                flickable = scroll_view.property('contentItem')
                flickable.setProperty('contentY', flickable.property('contentHeight') - flickable.property('height'))
                QTest.qWait(60)
                assert flickable.property('contentY') > 0
                last_launch = find('launchHoudini_1')
                last_point = last_launch.mapToScene(QPointF(0, 0))
                scroll_point = scroll_view.mapToScene(QPointF(0, 0))
                assert scroll_point.y() <= last_point.y()
                assert last_point.y() + last_launch.height() <= scroll_point.y() + scroll_view.height() + 1
                view.grab().save(str(state / 'houdini-menu-height-limit.png'))
                QTest.keyClick(view, Qt.Key_Escape)
                controller.update_houdini_connection(sessions=discovered)
                view.resize(1180, 820)
                QTest.qWait(80)
                click(connection)
                QTest.qWait(80)
                assert_menu_anchor()
                assert not scrollbar.property('visible')
                assert flickable.property('contentY') == 0
                controller.houdiniAction('connect')
                coordinator._on_poll_result({'status': 'ok', 'houdini': '22.0.429'})
                assert controller.houdiniConnection['port'] == 45172
                QTest.keyClick(view, Qt.Key_Escape)
                click(connection)
                click(find('houdiniSession_45173'))
                assert not menu.property('visible')
                assert controller.houdiniConnection['state'] == 'connecting'
                # A stale automatic probe must not override the user's choice.
                coordinator._probe_port = None
                coordinator._on_poll_result({'status': 'ok', 'houdini': 'old'})
                assert controller.houdiniConnection['state'] == 'connecting'
                coordinator._probe_port = 45173
                coordinator._on_poll_result({'status': 'ok', 'houdini': '22.0.429'})
                assert controller.houdiniConnection['state'] == 'connected'
                assert controller.houdiniConnection['port'] == 45173
                assert find('houdiniStatusDot').property('color') == find('houdiniStatusLabel').property('color')
                assert find('houdiniStatusDot').property('color').name() == '#27d769'
                assert '22.0.429' in connection.property('description')
                click(connection)
                click(find('houdiniSession_45174'))
                coordinator._probe_port = 45174
                coordinator._on_poll_result({'status': 'ok', 'houdini': '21.0.631'})
                assert controller.houdiniConnection['port'] == 45174
                assert os.environ['HAGENT_BRIDGE_PORT'] == '45174'
                click(connection)
                click(find('disconnectHoudini'))
                assert controller.houdiniConnection['state'] == 'disconnected'
                assert controller.houdiniConnection['paused']
                coordinator._on_poll_result({'status': 'ok', 'houdini': 'stale'})
                assert controller.houdiniConnection['state'] == 'disconnected'
                with patch.object(doctor, 'ensure_connected') as heal:
                    assert not controller._heal_bridge()
                    assert not controller._run_connection_tool('repair_houdini_connection', {'action': 'reconnect'})['success']
                    heal.assert_not_called()
                click(connection)
                click(find('houdiniSession_45174'))
                coordinator._probe_port = 45174
                coordinator._on_poll_result({'status': 'ok', 'houdini': '21.0.631'})
                assert not controller.houdiniConnection['paused']
                assert controller.houdiniConnection['port'] == 45174
                # Failure to switch preserves the current working session.
                coordinator.connection_action('connect:45173')
                coordinator._probe_port = 45173
                coordinator._on_poll_result(None)
                assert controller.houdiniConnection['state'] == 'connected'
                assert controller.houdiniConnection['port'] == 45174
                coordinator.connection_action('connect:45173')
                coordinator._probe_port = 45173
                controller._running = True
                coordinator._on_poll_result({'status': 'ok', 'houdini': '22.0.429'})
                assert controller.houdiniConnection['port'] == 45174
                assert controller.houdiniConnection['state'] == 'connected'
                controller._running = False
                click(connection)
                QTest.qWait(140)
                view.grab().save(str(state / 'houdini-connection-menu.png'))
                QTest.keyClick(view, Qt.Key_Escape)
                coordinator._probe_port = None
                coordinator._on_poll_result(None)
                coordinator._on_poll_result(None)
                assert controller.houdiniConnection['state'] == 'disconnected'
                assert find('houdiniStatusDot').property('color').name() == '#ff4d4f'
                launch.return_value = SimpleNamespace(poll=MagicMock(return_value=None))
                click(connection)
                click(find('launchHoudini_1'))
                launch.assert_called_once_with(str(state), installs[1])
                assert controller.houdiniConnection['state'] == 'launching'
                coordinator._on_poll_result(None)
                assert controller.houdiniConnection['state'] == 'launching'
                coordinator._on_poll_result({'status': 'ok', 'houdini': '21.0.631'})
                assert controller.houdiniConnection['state'] == 'connected'
                # A process that exits before its Bridge connects must unlock
                # launch actions so the same version can be tried again.
                coordinator._on_bridge_lost()
                launch.reset_mock()
                process = SimpleNamespace(poll=MagicMock(return_value=None))
                launch.return_value = process
                coordinator.connection_action('launch:1')
                process.poll.return_value = 1
                coordinator._check_launch()
                assert controller.houdiniConnection['state'] == 'disconnected'
                click(connection)
                assert find('launchHoudini_1').isEnabled()
                process.poll.return_value = None
                click(find('launchHoudini_1'))
                assert launch.call_count == 2
                assert controller.houdiniConnection['state'] == 'launching'
                with patch.object(external.time, 'monotonic', return_value=coordinator._launch_deadline + 1):
                    coordinator._check_launch()
                assert controller.houdiniConnection['state'] == 'disconnected'
                assert not coordinator._launch_watch.isActive()
                coordinator.connection_action('launch:1')
                process.poll.return_value = 0
                with patch.object(external.time, 'monotonic', return_value=coordinator._launch_started_at + 4), \
                     patch.object(external, 'is_houdini_running', return_value=True):
                    coordinator._check_launch()
                assert controller.houdiniConnection['state'] == 'launching'
                with patch.object(external.time, 'monotonic', return_value=coordinator._launch_started_at + 4), \
                     patch.object(external, 'is_houdini_running', return_value=False):
                    coordinator._check_launch()
                assert controller.houdiniConnection['state'] == 'disconnected'
                process.poll.return_value = None
                launch.side_effect = OSError('Offline launch fixture')
                coordinator.connection_action('launch:0')
                assert controller.houdiniConnection['state'] == 'disconnected'
                launch.side_effect = None
                launch.reset_mock()
                coordinator.connection_action('launch:0')
                launch.assert_called_once_with(str(state), installs[0])
                coordinator._on_poll_result({'status': 'ok', 'houdini': '22.0.429'})
                assert not coordinator._launch_watch.isActive()
                controller._running = True
                controller.runningChanged.emit()
                controller.houdiniAction('launch:0')
                assert launch.call_count == 1
                controller._running = False
                controller.runningChanged.emit()
                controller.requestHoudiniAction.disconnect(coordinator.connection_action)
            controller.update_houdini_connection(state='disconnected', version='', port=0,
                                                sessions=[], installs=[], external=False)
            # One header entry owns settings. Switches retain live bindings and
            # differ by track, thumb position and check mark in either theme.
            open_settings()
            preferences = find('settingsWindow')
            assert preferences.property('visible')
            assert preferences.property('sec') == 'general'
            toggle = find('thinkingToggle')
            initial_thinking = controller.showThinking
            assert toggle.property('checked') == initial_thinking
            for theme in ['graphite', 'day']:
                controller.setAppTheme(theme)
                QTest.qWait(40)
                assert view.quickWindow().color() == root.property('color')
                before = find('switchTrack', toggle).property('color')
                thumb_before = find('switchThumb', toggle).property('x')
                click(toggle)
                QTest.qWait(150)
                assert controller.showThinking != initial_thinking
                assert toggle.property('checked') == controller.showThinking
                assert before != find('switchTrack', toggle).property('color')
                assert thumb_before != find('switchThumb', toggle).property('x')
                toggle.forceActiveFocus()
                QTest.keyClick(view, Qt.Key_Space)
                QTest.qWait(150)
                assert controller.showThinking == initial_thinking
                assert toggle.property('checked') == initial_thinking
            controller.setAppTheme('graphite')
            # Theme and accent choices must recolor actual UI surfaces, rather
            # than only moving a neutral selection pill in the settings page.
            click(find('settingsNav_appearance'))
            for key, background, composer_color in [
                ('noir', '#0d0d0d', '#101010'),
                ('midnight', '#0c0e13', '#10131a'),
                ('day', '#ffffff', '#f7f7f7'),
                ('graphite', '#212121', '#2c2c2c'),
            ]:
                option = find('appearanceOption_' + key)
                click(option)
                assert controller.appTheme == key and settings.value('app_theme') == key
                assert root.property('color').name() == background
                assert find('composerCard').property('color').name() == composer_color
                assert option.property('on') and option.property('color') == option.property('dot')
                other = find('appearanceOption_' + ('day' if key != 'day' else 'noir'))
                assert not other.property('on') and other.property('color') != other.property('dot')
            model.load(module.wrap_ai_rows([{'type': 'user', 'payload': {'text': 'Appearance preview'}}]))
            QTest.qWait(60)
            bubble_colors = set()
            for key in ['warm', 'steel', 'celadon', 'clay', 'neutral']:
                option = find('appearanceOption_' + key)
                click(option)
                assert controller.accentKey == key and settings.value('accent_key') == key
                assert option.property('on') and option.property('color') == option.property('dot')
                bubble_colors.add(find('userMessageBubble').property('color').name())
            assert len(bubble_colors) == 5, bubble_colors
            click(find('appearanceOption_mono'))
            assert controller.fontFamilyKey == 'mono'
            click(find('appearanceOption_modern'))
            assert controller.fontFamilyKey == 'modern'
            click(find('appearanceOption_compact'))
            compact_height = find('composerCard').height()
            click(find('appearanceOption_roomy'))
            assert controller.densityKey == 'roomy'
            assert find('composerCard').height() > compact_height
            click(find('appearanceOption_normal'))
            # Header actions are still reachable after moving into settings;
            # browser / network / filesystem writes are mocked at their boundary.
            click(find('settingsNav_meshy'))
            assert find('meshySettings').property('visible')
            with patch.object(controller, 'openMeshy') as open_meshy:
                click(find('meshyLink_workspace'))
                open_meshy.assert_called_once_with('workspace')
            with patch.object(controller, 'openMeshyLogin', wraps=controller.openMeshyLogin) as open_meshy_login:
                click(find('meshyConfigureKey'))
                open_meshy_login.assert_called_once()
                assert preferences.property('visible')
                assert find('actionDialog').property('visible')
                QTest.keyClick(view, Qt.Key_Escape)
                QTest.qWait(60)
                assert not find('actionDialog').property('visible')
                assert preferences.property('visible') and preferences.property('sec') == 'meshy'
            click(find('settingsNav_templates'))
            click(find('settingsOpenTemplates'))
            assert preferences.property('visible')
            assert find('templateLibrary').property('visible')
            assert find('backFromTemplates').property('visible')
            click(find('backFromTemplates'))
            assert not find('templateLibrary').property('visible')
            assert preferences.property('visible') and preferences.property('sec') == 'templates'
            click(find('settingsOpenTemplates'))
            click(find('closeTemplateLibrary'))
            assert preferences.property('visible')
            click(find('settingsOpenTemplates'))
            QTest.keyClick(view, Qt.Key_Escape)
            QTest.qWait(60)
            assert not find('templateLibrary').property('visible')
            assert preferences.property('visible')
            click(find('settingsOpenTemplates'))
            click(find('insertTemplateAction'))
            assert not find('templateLibrary').property('visible')
            assert not preferences.property('visible')
            assert find('messageInput').property('text')
            find('messageInput').setProperty('text', '')
            open_settings()
            for section in ['appearance', 'sessions', 'rules', 'plugins', 'memory', 'about']:
                click(find('settingsNav_' + section))
                assert preferences.property('sec') == section
            # Informational children return to the same settings section.
            click(find('settingsCacheLocation'))
            info = find('infoDialog')
            assert info.property('visible') and preferences.property('visible')
            QTest.keyClick(view, Qt.Key_Escape)
            QTest.qWait(60)
            assert not info.property('visible')
            assert preferences.property('visible') and preferences.property('sec') == 'about'
            click(find('settingsNav_sessions'))
            click(find('settingsTokenAnalysis'))
            assert find('tokenPopup').property('visible') and preferences.property('visible')
            QTest.keyClick(view, Qt.Key_Escape)
            QTest.qWait(60)
            assert not find('tokenPopup').property('visible')
            assert preferences.property('visible') and preferences.property('sec') == 'sessions'
            # Error messages must not replace an editable form, or disappear
            # when its confirmation handler finishes closing the original.
            dialog = find('actionDialog')
            with patch.object(controller, '_session', SimpleNamespace(client=MagicMock())):
                controller.openCustomProviderDialog.emit('https://example.com/v1', '', 'gpt-test', False, '128000', False)
                QTest.qWait(60)
                click(find('submitCustomDialog', dialog))
                assert dialog.property('mode') == 'custom' and dialog.property('visible')
                assert info.property('visible')
                QTest.keyClick(view, Qt.Key_Escape)
                QTest.qWait(60)
                assert not info.property('visible') and dialog.property('visible')
                assert dialog.property('mode') == 'custom'
                QTest.keyClick(view, Qt.Key_Escape)
                QTest.qWait(60)
                assert not dialog.property('visible') and preferences.property('visible')
            def fail_confirmation():
                raise RuntimeError('Offline confirmation failure')
            controller._confirm_actions['test-menu-error'] = fail_confirmation
            controller.openConfirmDialog.emit('Test confirm', 'Offline fixture', 'test-menu-error')
            QTest.qWait(60)
            assert not find('dontAskDeleteSession', dialog).property('visible')
            click(find('confirmDialogButton', dialog))
            assert not dialog.property('visible') and info.property('visible')
            assert 'Offline confirmation failure' in info.property('body')
            QTest.keyClick(view, Qt.Key_Escape)
            QTest.qWait(60)
            assert preferences.property('visible')
            with patch.object(controller, 'subscriptionDialogOpened'), \
                 patch.object(controller, 'subscriptionStatus', return_value={'title': 'Offline subscription', 'accounts': [], 'busy': False}):
                controller.openSubscriptionDialog.emit()
                QTest.qWait(60)
                assert find('subscriptionDialog').property('visible')
                QTest.keyClick(view, Qt.Key_Escape)
                QTest.qWait(60)
                assert not find('subscriptionDialog').property('visible')
                assert preferences.property('visible')
            rules = [
                {'id': 'test-one', 'title': 'One', 'content': 'Original one', 'readonly': False, 'enabled': True},
                {'id': 'test-two', 'title': 'Two', 'content': 'Original two', 'readonly': False, 'enabled': True},
            ]
            with patch.object(controller, 'rulesItems', return_value=rules), \
                 patch.object(controller, 'saveRule') as save_rule:
                click(find('settingsNav_rules'))
                editor = find('ruleContentEditor', preferences)
                editor.setProperty('text', 'Unsaved draft')
                click(find('ruleRow_test-two'))
                assert editor.property('text') == 'Unsaved draft'
                click(find('cancelRuleEdit', preferences))
                assert editor.property('text') == 'Original one'
                click(find('ruleRow_test-two'))
                assert editor.property('text') == 'Original two'
                save_rule.assert_not_called()
            plugins = [{'name': 'test-plugin', 'enabled': True, 'description': 'Offline fixture'}]
            def save_plugin(name, enabled):
                assert name == 'test-plugin'
                plugins[0]['enabled'] = enabled
                controller.managementChanged.emit()
            with patch.object(controller, 'pluginItems', return_value=plugins), \
                 patch.object(controller, 'setPluginEnabled', side_effect=save_plugin) as set_plugin:
                click(find('settingsNav_plugins'))
                click(find('entryToggle_test-plugin'))
                assert set_plugin.call_args.args == ('test-plugin', False)
                assert not find('entryToggle_test-plugin').property('checked')
                click(find('entryToggle_test-plugin'))
                assert set_plugin.call_args.args == ('test-plugin', True)
                assert find('entryToggle_test-plugin').property('checked')
            click(find('settingsCloseButton'))
            # Compact settings use the full width and keep section navigation.
            for width, scale in [(440, 1.0), (360, 1.3)]:
                controller.setFontScale(scale)
                view.resize(width, 820)
                QTest.qWait(60)
                open_settings()
                assert preferences.property('compact')
                assert not find('settingsNavigation').property('visible')
                click(find('settingsSectionSelector'))
                click(find('menuItem_general'))
                toggle = find('thinkingToggle')
                for name in ['thinkingToggle', 'cookToggle', 'memoryToggle']:
                    switch = find(name)
                    point = switch.mapToScene(QPointF(0, 0))
                    assert switch.width() == toggle.width() and switch.height() == toggle.height()
                    assert 0 <= point.x() <= view.width() - switch.width()
                click(find('settingsSectionSelector'))
                click(find('menuItem_templates'))
                click(find('settingsOpenTemplates'))
                assert find('backFromTemplates').property('visible')
                click(find('backFromTemplates'))
                assert preferences.property('visible') and preferences.property('sec') == 'templates'
                click(find('settingsSectionSelector'))
                click(find('menuItem_model'))
                providers = find('settingsProviders')
                custom_rows = [dict(id='align-one', name='GPT 6', active=True, configured=True,
                                    models=[dict(name='gpt-test', context=128000, vision=False)], anthropic=False)]
                with patch.object(controller, 'customProviderItems', return_value=custom_rows):
                    for language in ['zh', 'en']:
                        controller._lang = language
                        controller.langChanged.emit()
                        QMetaObject.invokeMethod(providers, 'reload')
                        QTest.qWait(60)
                        keys = [item['key'] for item in controller.builtinProviderItems()] + ['custom:align-one']
                        for prefix in ['providerSelect_', 'providerConfig_']:
                            cells = [find(prefix + key, providers) for key in keys]
                            positions = [cell.mapToScene(QPointF(0, 0)).x() for cell in cells]
                            assert max(positions) - min(positions) < 1, (language, prefix, positions)
                            assert max(cell.width() for cell in cells) - min(cell.width() for cell in cells) < 1
                        if language == 'zh':
                            view.grab().save(str(state / ('provider-columns-' + str(width) + '.png')))
                    controller._lang = 'zh'
                    controller.langChanged.emit()
                    QMetaObject.invokeMethod(providers, 'reload')
                QMetaObject.invokeMethod(providers, 'startAdd')
                QTest.qWait(60)
                # The real form writes vision choices back into its model.
                vision = find('providerVisionToggle_0')
                model_name_input = find('providerModelName_0_input')
                model_name_input.forceActiveFocus()
                QTest.keyClicks(view, 'gpt-test')
                vision.forceActiveFocus()
                QTest.keyClick(view, Qt.Key_Space)
                QTest.qWait(40)
                assert vision.property('checked')
                with patch.object(controller, 'saveCustomProvider', return_value={'ok': True}) as save:
                    click(find('saveProviderButton'))
                    payload = json.loads(save.call_args.args[0])
                    assert payload['models'] == [{'name': 'gpt-test', 'context': 128000, 'vision': True}]
                click(find('settingsCloseButton'))
            controller.setFontScale(1.0)
            view.resize(1180, 820)
            QTest.qWait(60)
            docked = find('dockedSidebar')
            assert docked.property('visible')
            assert root.findChild(QObject, 'sidebarCollapse') is None
            assert root.findChild(QObject, 'sidebarToggle') is None
            before_sidebar = docked.width()
            before_chat = find('chatViewport').width()
            drag_sidebar(84)
            assert docked.width() > before_sidebar + 60
            assert find('chatViewport').width() < before_chat - 60
            drag_sidebar(-84)
            assert abs(docked.width() - before_sidebar) < 2
            click(find('newChatButton', docked))
            assert len(controller._sessions) == 2
            search = find('sessionSearch', docked)
            search.setProperty('text', 'no-matching-chat')
            QTest.qWait(40)
            assert find('sidebarSessions', docked).property('count') == 0
            search.setProperty('text', '')
            QTest.qWait(40)
            assert find('sidebarSessions', docked).property('count') == 2
            # Crossing the old hover gap must not hide the delete hit area or
            # restore the timestamp while the pointer is still inside the row.
            hovered_rows = []  # Keep visual-only delegate wrappers alive in PySide.
            def hover_delete(index):
                row = find('sessionRow_' + str(index), docked)
                button = find('deleteSession_' + str(index), row)
                timestamp = find('sessionTime_' + str(index), row)
                hovered_rows.append((row, button, timestamp))
                start = row.mapToScene(QPointF(20, row.height()/2))
                QTest.mouseMove(view, start.toPoint())
                QTest.qWait(30)
                assert button.property('visible') and not timestamp.property('visible')
                end = button.mapToScene(QPointF(button.width()/2, button.height()/2))
                for step in range(1, 21):
                    point = start + (end - start) * (step / 20)
                    QTest.mouseMove(view, point.toPoint())
                    QTest.qWait(8)
                    assert button.property('visible') and not timestamp.property('visible'), step
                return button
            controller.setAskDeleteSession(True)
            click(hover_delete(0))
            assert len(controller._sessions) == 2
            assert find('actionDialog').property('visible')
            skip_delete = find('dontAskDeleteSession', find('actionDialog'))
            assert skip_delete.property('visible') and not skip_delete.property('checked')
            click(skip_delete)
            assert skip_delete.property('checked') and controller.askDeleteSession
            QTest.keyClick(view, Qt.Key_Escape)
            QTest.qWait(60)
            assert len(controller._sessions) == 2
            assert controller.askDeleteSession and not controller._session_delete_confirms
            QTest.mouseMove(view, QPointF(10, 10).toPoint())
            QTest.qWait(30)
            assert not find('deleteSession_0', docked).property('visible')
            assert find('sessionTime_0', docked).property('visible')
            click(hover_delete(0))
            skip_delete = find('dontAskDeleteSession', find('actionDialog'))
            assert not skip_delete.property('checked')
            click(skip_delete)
            click(find('confirmDialogButton', find('actionDialog')))
            assert len(controller._sessions) == 1
            assert not controller.askDeleteSession
            assert settings.value('ask_delete_session', type=bool) is False
            assert not controller._session_delete_confirms
            assert find('sidebarSessions', docked).property('count') == 1
            click(find('newChatButton', docked))
            assert len(controller._sessions) == 2
            controller._sessions[0]['title'] = 'Delete target'
            controller._sessions[1]['title'] = 'Keep target'
            controller.sessionsChanged.emit()
            search.setProperty('text', 'Delete target')
            QTest.qWait(40)
            assert find('sidebarSessions', docked).property('count') == 1
            controller.setAskDeleteSession(False)
            click(hover_delete(0))
            assert len(controller._sessions) == 1 and controller._sessions[0]['title'] == 'Keep target'
            assert not find('actionDialog').property('visible')
            search.setProperty('text', '')
            QTest.qWait(40)
            click(find('newChatButton', docked))
            assert len(controller._sessions) == 2
            open_settings()
            click(find('settingsNav_sessions'))
            restore_confirmation = find('confirmSessionDeleteToggle', preferences)
            assert not restore_confirmation.property('checked')
            click(restore_confirmation)
            assert controller.askDeleteSession and settings.value('ask_delete_session', type=bool)
            click(find('settingsCloseButton'))
            view.resize(440, 820)
            QTest.qWait(60)
            assert not root.property('wide')
            assert not docked.property('visible')
            drag_sidebar(180 * controller.fontScale)
            assert root.property('sidebarExpanded')
            assert docked.property('visible')
            click(find('newChatButton', docked))
            assert len(controller._sessions) == 3
            assert not root.property('sidebarExpanded')
            click(find('modeSelector'))
            assert find('modeMenu').property('visible')
            click(find('menuItem_Ask'))
            assert controller._mode == 'Ask'
            original_models = list(module.MODEL_MAP['duojie'])
            module.MODEL_MAP['duojie'] = original_models + ['offline-model-%d' % i for i in range(40)]
            click(find('modelSelector'))
            menu = find('modelMenu')
            assert menu.property('visible')
            assert not find('effortSlider').property('visible')
            assert controller.reasoningEffort == ''
            controller.setReasoningEffort('high')
            assert controller.reasoningEffort == ''
            assert menu.property('height') <= view.height() - 24
            top = find('composerCard').mapToScene(QPointF(0, 0)).y() + menu.property('y')
            assert top >= 0 and top + menu.property('height') <= view.height(), (top, menu.property('y'), menu.property('height'), menu.property('maximumHeight'), find('composerCard').mapToScene(QPointF(0, 0)).y())
            model_id = controller.modelItems()[0]['val']
            assert controller.modelNameLabel('gpt-6.1-sol') == 'GPT-6.1-Sol'
            assert controller.modelNameLabel('gpt-6-astra') == 'GPT-6-Astra'
            assert controller.modelNameLabel('openai/gpt-6-astra') == 'OpenAI/GPT-6-Astra'
            assert controller.modelItems()[0]['label'] == controller.modelNameLabel(model_id)
            click(find('menuItem_' + model_id))
            assert controller.model == model_id
            assert controller.modelDisplayName == controller.modelNameLabel(model_id)
            assert find('modelSelector').property('label') == controller.modelNameLabel(model_id)
            module.MODEL_MAP['duojie'] = original_models
            # Reasoning and model choice share one popover, including defaults
            # and per-model effort ranges / persisted selections.
            controller._provider = 'codex'
            controller._model_name = 'gpt-6.1-sol'
            controller.providerChanged.emit()
            controller.modelChanged.emit()
            QTest.qWait(60)
            assert root.findChild(QObject, 'effortSelector') is None
            assert root.findChild(QObject, 'effortMenu') is None
            controller.setReasoningEffort('high')
            click(find('modelSelector'))
            slider = find('effortSlider')
            assert slider.property('visible')
            assert slider.property('to') == 5
            assert slider.property('value') == 2
            assert find('pickerModelSelector').property('label') == 'GPT-6.1-Sol'
            account = next(item for item in controller.modelItems() if item.get('val') == '__sub_account__')
            assert 'ChatGPT' in account['label']
            click(find('resetEffortButton'))
            assert slider.property('value') == 0
            slider.forceActiveFocus()
            QTest.keyClick(view, Qt.Key_Right)
            QTest.keyClick(view, Qt.Key_Right)
            QTest.qWait(40)
            assert controller.reasoningEffort == 'high'
            assert find('modelMenu').property('visible')
            click(find('resetEffortButton'))
            assert controller.reasoningEffort == 'low'
            slider.forceActiveFocus()
            QTest.keyClick(view, Qt.Key_Right)
            QTest.keyClick(view, Qt.Key_Right)
            QTest.qWait(40)
            assert controller.reasoningEffort == 'high', (controller.reasoningEffort, slider.property('value'))
            click(find('pickerModelSelector'))
            click(find('menuItem_gpt-5.5'))
            assert controller.model == 'gpt-5.5'
            assert settings.value('last_model') == 'gpt-5.5'
            assert slider.property('to') == 3
            assert controller.reasoningEffort == 'medium'
            assert slider.property('value') == 1
            slider.forceActiveFocus()
            QTest.keyClick(view, Qt.Key_Right)
            QTest.keyClick(view, Qt.Key_Right)
            QTest.qWait(40)
            assert controller.reasoningEffort == 'xhigh', (controller.reasoningEffort, slider.property('value'), slider.property('to'), find('modelMenu').property('effortIndex'))
            click(find('pickerModelSelector'))
            click(find('menuItem_gpt-6.1-sol'))
            assert controller.model == 'gpt-6.1-sol', controller.model
            assert controller.reasoningEffort == 'high', (controller.reasoningEffort, dict(controller._effort_by_model))
            assert slider.property('value') == 2
            assert find('modelSelector').property('detail') == controller.reasoningEffortLabel.split(' · ')[-1]
            QTest.keyClick(view, Qt.Key_Escape)
            QTest.qWait(40)
            assert not find('modelMenu').property('visible')
            # Context detail is available only on hover and uses the live
            # conversation estimate / model capacity, including exact counts.
            usage = find('contextUsage')
            tooltip = find('contextUsageTooltip')
            QTest.mouseMove(view, QPointF(10, 10).toPoint())
            QTest.qWait(40)
            assert not tooltip.property('visible')
            assert not find('modeSelector').property('active')
            with patch.object(controller, '_estimate_ctx', return_value=99300), \
                 patch.object(controller, '_context_limit', return_value=128000):
                controller.tokensChanged.emit()
                QTest.qWait(40)
                assert usage.property('used') == 99300
                assert usage.property('limit') == 128000
                assert abs(usage.property('fraction') - 99300/128000) < 0.0001
                point = usage.mapToScene(QPointF(usage.width()/2, usage.height()/2)).toPoint()
                QTest.mouseMove(view, point)
                QTest.qWait(450)
                assert tooltip.property('visible')
                detail = tooltip.property('text').replace(',', '').replace('\u00a0', '').replace('\u202f', '')
                assert '99300' in detail and '128000' in detail and '78%' in detail, detail
                QTest.mouseMove(view, QPointF(10, 10).toPoint())
                QTest.qWait(40)
                assert not tooltip.property('visible')
            controller.tokensChanged.emit()
            # All composer controls share a height and vertical center. Selectors
            # are full capsules; attachment / send hit areas are true circles.
            for scale, width in [(1.0, 1180), (1.0, 440), (1.3, 360)]:
                controller.setFontScale(scale)
                view.resize(width, 820)
                QTest.qWait(60)
                send = find('sendButton')
                attachment = find('attachmentButton')
                mode_control = find('modeSelector')
                model_control = find('modelSelector')
                attachment_right = attachment.mapToScene(QPointF(attachment.width(), 0)).x()
                mode_left = mode_control.mapToScene(QPointF(0, 0)).x()
                mode_right = mode_control.mapToScene(QPointF(mode_control.width(), 0)).x()
                model_left = model_control.mapToScene(QPointF(0, 0)).x()
                model_right = model_control.mapToScene(QPointF(model_control.width(), 0)).x()
                usage_left = usage.mapToScene(QPointF(0, 0)).x()
                usage_right = usage.mapToScene(QPointF(usage.width(), 0)).x()
                send_left = send.mapToScene(QPointF(0, 0)).x()
                assert attachment_right <= mode_left < mode_right <= usage_left < usage_right <= model_left < model_right <= send_left
                assert mode_left - attachment_right < 12 * scale
                assert model_left - usage_right < 12 * scale
                assert send_left - model_right < 12 * scale
                center_y = send.mapToScene(QPointF(0, send.height()/2)).y()
                for name in ['attachmentButton', 'modelSelector', 'modeSelector', 'sendButton', 'contextUsage']:
                    control = find(name)
                    assert abs(control.height() - send.height()) < 1, (name, control.height(), send.height())
                    assert abs(control.mapToScene(QPointF(0, control.height()/2)).y() - center_y) < 1, name
                    if name in ['attachmentButton', 'sendButton']:
                        assert abs(control.width() - control.height()) < 1
                        assert abs(control.property('radius') - control.height()/2) < 1
                    elif name != 'contextUsage':
                        background = find('pillBackground', control)
                        assert abs(background.property('radius') - control.height()/2) < 1
                        expression = QQmlExpression(qmlContext(background), background, 'border.width')
                        assert expression.evaluate()[0] == 0
            # Regression: an expanded sidebar plus larger text must never clip
            # the send/stop action, or any of the model and mode controls.
            for scale, width in [(1.3, 420), (1.6, 440), (1.3, 360)]:
                controller.setFontScale(scale)
                view.resize(width, 820)
                root.setProperty('sidebarExpanded', True)
                QTest.qWait(80)
                assert find('composer').property('compactToolbar')
                card = find('composerCard')
                origin = card.mapToScene(QPointF(0, 0))
                for name in ['attachmentButton', 'modeSelector', 'contextUsage', 'modelSelector', 'sendButton']:
                    control = find(name)
                    point = control.mapToScene(QPointF(0, 0))
                    assert origin.x() <= point.x() and point.x() + control.width() <= origin.x() + card.width(), (width, scale, name)
                    assert origin.y() <= point.y() and point.y() + control.height() <= origin.y() + card.height(), (width, scale, name)
                find('messageInput').setProperty('text', 'Narrow composer test')
                with patch.object(controller, 'send', return_value=True) as send_message:
                    click(find('sendButton'))
                    send_message.assert_called_once_with('Narrow composer test')
                stop_narrow = MagicMock()
                with patch.object(controller, '_session', SimpleNamespace(stop=stop_narrow)):
                    controller._set_running(True)
                    QTest.qWait(30)
                    click(find('sendButton'))
                    stop_narrow.assert_called_once()
                    controller._set_running(False)
            # Regression: previews must scroll instead of pushing the send/stop
            # controls below the minimum window, including long text and banners.
            import base64
            from PySide6.QtCore import QByteArray, QBuffer, QIODevice
            from PySide6.QtGui import QImage
            image = QImage(80, 40, QImage.Format_RGB32)
            image.fill(Qt.white)
            png = QByteArray()
            buffer = QBuffer(png)
            buffer.open(QIODevice.WriteOnly)
            assert image.save(buffer, 'PNG')
            sample = base64.b64encode(bytes(png)).decode('ascii')
            for width, scale, count, long_text, extra_status in [
                (420, 1.3, 6, False, False),
                (420, 1.6, 6, False, False),
                (420, 1.6, 1, True, False),
                (440, 1.6, 12, True, True),
                (1180, 1.0, 30, True, False),
            ]:
                controller.setFontScale(scale)
                controller.setDensityKey('roomy' if extra_status else 'normal')
                view.resize(width, 560)
                root.setProperty('sidebarExpanded', True)
                controller._pending_images = [(sample, 'image/png')] * count
                controller.imagesChanged.emit()
                controller._pending_ops = 3 if extra_status else 0
                controller.pendingOpsChanged.emit()
                controller._status_phase = 'generating' if extra_status else ''
                controller.statusChanged.emit()
                controller._update_info = 'Offline update fixture' if extra_status else ''
                controller._update_state = 'available' if extra_status else 'idle'
                controller.updateAvailableChanged.emit()
                prompt = ('Long image prompt.\n' * 80) if long_text else 'Describe these images'
                find('messageInput').setProperty('text', prompt)
                QTest.qWait(100)
                send_button = find('sendButton')
                point = send_button.mapToScene(QPointF(0, 0))
                assert point.x() >= 0 and point.x() + send_button.width() <= view.width()
                assert point.y() >= 0 and point.y() + send_button.height() <= view.height(), (width, scale, count, long_text, point.y())
                viewport = find('attachmentViewport')
                assert viewport.height() > 0
                with patch.object(controller, 'send', return_value=True) as send_images:
                    click(send_button)
                    send_images.assert_called_once_with(prompt)
                stop_images = MagicMock()
                with patch.object(controller, '_session', SimpleNamespace(stop=stop_images)):
                    controller._set_running(True)
                    QTest.qWait(30)
                    click(find('sendButton'))
                    stop_images.assert_called_once()
                    controller._set_running(False)
            controller._pending_ops = 0
            controller.pendingOpsChanged.emit()
            controller._status_phase = ''
            controller.statusChanged.emit()
            controller._update_info = ''
            controller._update_state = 'idle'
            controller.updateAvailableChanged.emit()
            controller.setFontScale(1.6)
            controller.setDensityKey('normal')
            view.resize(420, 560)
            root.setProperty('sidebarExpanded', True)
            controller._pending_images = [(sample, 'image/png')] * 6
            controller.imagesChanged.emit()
            QTest.qWait(100)
            viewport = find('attachmentViewport')
            assert viewport.property('contentHeight') > viewport.height()
            thumbnail = find('attachmentThumbnail_0')
            frame = view.grab().toImage()
            point = thumbnail.mapToScene(QPointF(0, 0))
            sx, sy = frame.width() / view.width(), frame.height() / view.height()
            def thumbnail_pixel(x, y):
                return frame.pixelColor(int((point.x() + x) * sx), int((point.y() + y) * sy))
            for x, y in [(1, thumbnail.height()/2), (thumbnail.width()/2, 1),
                         (thumbnail.width()/2, thumbnail.height()-1)]:
                pixel = thumbnail_pixel(x, y)
                assert min(pixel.red(), pixel.green(), pixel.blue()) > 240, (x, y, pixel.name())
            assert thumbnail_pixel(0, 0).name() == root.property('color').name()
            view.grab().save(str(state / 'reference-thumbnails-rounded.png'))
            click(find('attachmentThumbnail_0'))
            assert find('attachmentPreview').property('visible')
            QTest.keyClick(view, Qt.Key_Escape)
            QTest.qWait(60)
            assert not find('attachmentPreview').property('visible')
            flickable = viewport.property('contentItem')
            flickable.setProperty('contentY', flickable.property('contentHeight') - flickable.property('height'))
            QTest.qWait(60)
            last = find('removeAttachment_5')
            last_point = last.mapToScene(QPointF(last.width()/2, last.height()/2))
            viewport_point = viewport.mapToScene(QPointF(0, 0))
            assert viewport_point.y() <= last_point.y() <= viewport_point.y() + viewport.height()
            click(last)
            assert len(controller._pending_images) == 5
            controller.clearImages()
            QTest.qWait(60)
            assert not viewport.property('visible')
            root.setProperty('sidebarExpanded', False)
            controller.setFontScale(1.0)
            view.resize(440, 820)
            QTest.qWait(40)
            # Long input is bounded; the stop action reaches the active backend.
            input_item = find('messageInput')
            input_item.setProperty('text', '\n'.join(['节点与几何处理 test'] * 80))
            QTest.qWait(60)
            assert find('composer').height() < 320
            stop = MagicMock()
            controller._session = SimpleNamespace(stop=stop)
            controller._set_running(True)
            QTest.qWait(30)
            assert find('sendButton').property('busy')
            click(find('stopButton'))
            stop.assert_called_once()
            controller._set_running(False)
            controller._session = None
            input_item.setProperty('text', '')
            # During a turn both click and Enter enqueue without starting a
            # second worker; queue actions keep the current draft intact.
            model.clear()
            with patch.object(controller, '_simulate'):
                assert controller.send('Active turn')
                input_item.setProperty('text', 'Queued by click')
                click(find('sendButton'))
                assert input_item.property('text') == '' and controller.queuedCount == 1
                assert find('messageQueuePanel').isVisible()
                input_item.setProperty('text', 'Queued by Enter')
                input_item.forceActiveFocus()
                QTest.keyClick(view, Qt.Key_Return)
                QTest.qWait(60)
                assert controller.queuedCount == 2 and input_item.property('text') == ''
                entries = controller.queuedMessages
                click(find('removeQueuedMessage_' + entries[0]['id']))
                assert controller.queuedCount == 1
                input_item.setProperty('text', 'Current draft')
                click(find('editQueuedMessage_' + entries[1]['id']))
                assert controller.queuedCount == 0
                assert input_item.property('text') == 'Queued by Enter\n\nCurrent draft'
                # Independent stop stays accessible with a nonempty draft,
                # including a narrow window, large type and visible queue.
                for width, scale in [(420, 1.6), (710, 1.3), (1180, 1.0)]:
                    controller.setFontScale(scale)
                    view.resize(width, 820)
                    root.setProperty('sidebarExpanded', width < 1180)
                    input_item.setProperty('text', 'Another queued message')
                    click(find('sendButton'))
                    input_item.setProperty('text', 'Keep editing')
                    QTest.qWait(60)
                    for name in ['stopButton', 'sendButton', 'modelSelector', 'modeSelector']:
                        control = find(name)
                        point = control.mapToScene(QPointF(0, 0))
                        assert 0 <= point.x() and point.x() + control.width() <= view.width() + 1, (width, scale, name, point.x(), control.width())
                        assert 0 <= point.y() and point.y() + control.height() <= view.height() + 1
                view.grab().save(str(state / 'message-queue.png'))
                click(find('stopButton'))
                controller._ui_done('')
                QTest.qWait(60)
                assert controller.queuePaused and not controller.running
                click(find('resumeMessageQueue'))
                QTest.qWait(60)
                assert controller.running and controller.queuedCount == 2
                # Each successful completion starts exactly the next entry.
                controller._ui_done('')
                QTest.qWait(60)
                assert controller.running and controller.queuedCount == 1
                controller._ui_done('')
                QTest.qWait(60)
                assert controller.running and controller.queuedCount == 0
                controller._ui_done('')
                QTest.qWait(60)
                assert not controller.running and input_item.property('text') == 'Keep editing'
            controller.setFontScale(1.0)
            view.resize(440, 820)
            root.setProperty('sidebarExpanded', False)
            input_item.setProperty('text', '')
            # A failed real send exposes a copy action, local send time and a
            # draft recovery action; recovery preserves both draft and images.
            controller.setProvider('openai')
            model.clear()
            controller._pending_images = [(sample, 'image/png')]
            with patch.object(controller, '_simulate'):
                assert controller.send('请重新检查节点。')
            sent = model._items[0]['payload']
            assert sent['sent_at'] > 0 and sent['id'] and sent['images'][0].startswith('file:')
            controller._ui_done('HTTP 429: Too many pending requests, please retry later')
            QTest.qWait(100)
            assert model._items[0]['payload']['failed']
            assert find('sentTime_0').property('text')
            click(find('copyUserMessage_0'))
            assert app.clipboard().text() == '请重新检查节点。'
            input_item.setProperty('text', '保留现有草稿')
            controller._pending_images = [('eA==', 'image/png')]
            click(find('restoreFailedMessage_' + sent['id']))
            assert input_item.property('text') == '请重新检查节点。\n\n保留现有草稿'
            assert len(controller._pending_images) == 2
            assert controller._pending_images[1] == (sample, 'image/png')
            # Recovery itself does not send, change mode or duplicate attachments.
            assert not controller.running
            assert controller.restoreFailedMessage(sent['id'])
            assert len(controller._pending_images) == 2
            assert input_item.property('text') == '请重新检查节点。\n\n保留现有草稿'
            serialized = controller._serialize_rows()
            model.load(module.wrap_ai_rows(serialized))
            QTest.qWait(80)
            assert find('sentTime_0').property('text')
            assert find('restoreFailedMessage_' + sent['id']).isVisible()
            controller.clearImages()
            input_item.setProperty('text', '')
            # The right rail navigates user turns and stays anchored while
            # asynchronously loaded / updated earlier rows change their heights.
            history = []
            for index in range(20):
                history.extend([
                    {'type': 'user', 'payload': {'text': 'History prompt %d' % index}},
                    {'type': 'ai', 'payload': {'blocks': [{'kind': 'prose', 'html': '<p>%s</p>' % ('Scene details. ' * 60)}]}},
                ])
            model.load(module.wrap_ai_rows(history))
            QTest.qWait(400)
            chat = find('chatViewport')
            rail = find('chatTimeline')
            assert rail.property('visible') and rail.property('count') == 20
            assert chat.property('contentY') > chat.height()
            # History and the input card share both edges, including the
            # right-hand timeline gutter, sidebar resizing and large fonts.
            for width, scale, sidebar, density in [(1180, 1.0, False, 'normal'), (710, 1.3, True, 'normal'),
                                                   (420, 1.6, True, 'normal'), (420, 1.6, True, 'roomy')]:
                controller.setFontScale(scale)
                controller.setDensityKey(density)
                view.resize(width, 820)
                root.setProperty('sidebarExpanded', sidebar)
                QTest.qWait(100)
                card = find('composerCard')
                message_row = find('chatMessage_1')
                card_left = card.mapToScene(QPointF(0, 0)).x()
                message_left = message_row.mapToScene(QPointF(0, 0)).x()
                assert abs(card_left - message_left) < 1.1, (width, scale, card_left, message_left)
                assert abs(card.width() - message_row.width()) < 1.1, (width, scale, card.width(), message_row.width())
                for control_name in ['sendButton', 'contextUsage', 'modelSelector', 'modeSelector', 'attachmentButton']:
                    control = find(control_name)
                    control_left = control.mapToScene(QPointF(0, 0)).x()
                    assert control_left >= card_left and control_left + control.width() <= card_left + card.width() + 1, (width, scale, density, control_name, card_left, card.width(), control_left, control.width())
                if width == 1180:
                    view.grab().save(str(state / 'history-composer-aligned.png'))
            controller.setFontScale(1.0)
            controller.setDensityKey('normal')
            view.resize(440, 820)
            root.setProperty('sidebarExpanded', False)
            QTest.qWait(100)
            click(find('chatMarker_0', rail))
            assert chat.property('jumpTarget') == 0 and not chat.property('stick')
            assert chat.property('contentY') < 40
            click(find('chatMarker_20', rail))
            message = find('chatMessage_20')
            assert chat.property('jumpTarget') == 20
            assert abs(chat.property('contentY') - (message.property('topInContent') - 12)) < 3
            before_jump_y = chat.property('contentY')
            model.update_payload(0, {'text': 'Expanded earlier prompt.\n' * 35})
            QTest.qWait(150)
            assert chat.property('contentY') > before_jump_y + 100
            assert abs(chat.property('contentY') - (message.property('topInContent') - 12)) < 3
            model.append(module.wrap_ai_rows([{'type': 'ai', 'payload': {'blocks': [{'kind': 'prose', 'html': '<p>New reply</p>'}]}}])[0])
            QTest.qWait(100)
            assert chat.property('jumpTarget') == 20 and not chat.property('stick')
            model.clear()
            QTest.qWait(80)
            assert not rail.property('visible') and rail.property('count') == 0
            assert chat.property('jumpTarget') == -1 and chat.property('stick')
            # Render user / assistant delegates, including tool and prose blocks.
            model.load(module.wrap_ai_rows([
                {'type': 'user', 'payload': {'text': '检查选中的节点并解释参数。'}},
                {'type': 'ai', 'payload': {'blocks': [
                    {'kind': 'thinking', 'text': '读取节点结构。', 'dur': '1s'},
                    {'kind': 'exec', 'label': '检查场景', 'tools': [{'name': 'read_selection', 'state': 'done', 'detail': 'OK'}]},
                    {'kind': 'prose', 'html': '<p>节点检查结果与 <b>参数说明</b>。</p>'},
                ]}},
            ]))
            QTest.qWait(120)
            # At screenshot-sized / high-DPI widths, opening navigation must
            # reflow the existing conversation and composer instead of covering it.
            for scale, width in [(1.0, 710), (1.3, 710), (1.0, 440), (1.0, 1180)]:
                controller.setFontScale(scale)
                view.resize(width, 820)
                root.setProperty('sidebarExpanded', False)
                QTest.qWait(50)
                chat = find('chatViewport')
                full_width = chat.width()
                drag_sidebar(180 * controller.fontScale)
                assert docked.property('visible')
                right_edge = docked.mapToScene(QPointF(docked.width(), 0)).x()
                pane = find('conversationPane')
                assert pane.mapToScene(QPointF(0, 0)).x() >= right_edge - 1
                assert chat.width() < full_width - 100
                for name in ['chatViewport', 'composerCard']:
                    item = find(name)
                    left = item.mapToScene(QPointF(0, 0)).x()
                    assert left >= right_edge - 1, (scale, width, name, left, right_edge)
                    assert left + item.width() <= view.width() + 1
                status_label = find('houdiniStatusLabel')
                assert status_label.width() >= status_label.implicitWidth(), (width, scale, status_label.width(), status_label.implicitWidth())
                for name in ['houdiniConnectionButton', 'settingsButton']:
                    item = find(name)
                    left = item.mapToScene(QPointF(0, 0)).x()
                    assert left >= 0 and left + item.width() <= view.width() + 1
                drag_sidebar(-docked.width() - 100)
                assert not docked.property('visible')
                assert abs(chat.width() - full_width) < 1
            controller.setAppTheme('day')
            QTest.qWait(40)
            assert root.property('color').name() == '#ffffff'
            controller.setFontScale(1.3)
            QTest.qWait(40)
            view.resize(360, 720)
            QTest.qWait(60)
            assert find('composerCard').width() <= view.width()
            for name in ['modelSelector', 'modeSelector', 'sendButton']:
                control = find(name)
                point = control.mapToScene(QPointF(0, 0))
                assert point.x() >= 0 and point.x() + control.width() <= view.width(), (name, point.x(), control.width(), view.width())
            assert not warnings, '\n'.join(warnings)
            view.close()
        print('QML shell interactions passed')
    """)
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
               QT_QUICK_CONTROLS_STYLE="Basic", QML_DISABLE_DISK_CACHE="1",
               HAGENT_TELEMETRY_OFF="1")
    repo_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    # Keep the expanded interaction suite below Windows' command-line limit.
    script_path = tmp_path / "qml_shell_case.py"
    script_path.write_text(code, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", str(script_path), str(tmp_path)],
        cwd=repo_root, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
