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
            # One header entry owns settings. Switches retain live bindings and
            # differ by track, thumb position and check mark in either theme.
            click(find('settingsButton'))
            preferences = find('settingsWindow')
            assert preferences.property('visible')
            assert preferences.property('sec') == 'general'
            toggle = find('thinkingToggle')
            initial_thinking = controller.showThinking
            assert toggle.property('checked') == initial_thinking
            for theme in ['graphite', 'day']:
                controller.setAppTheme(theme)
                QTest.qWait(40)
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
            click(find('settingsButton'))
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
                click(find('settingsButton'))
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
            click(find('settingsButton'))
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
            image = QImage(1, 1, QImage.Format_RGB32)
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
            click(find('sendButton'))
            stop.assert_called_once()
            controller._set_running(False)
            controller._session = None
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
