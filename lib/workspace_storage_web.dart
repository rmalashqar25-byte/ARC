import 'package:web/web.dart' as web;

const _key = 'arc.workspace.v1';

String? readWorkspace() => web.window.localStorage.getItem(_key);

bool writeWorkspace(String value) {
  web.window.localStorage.setItem(_key, value);
  return true;
}
