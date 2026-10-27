#!/usr/bin/env python3
"""Build-pinned offline campaign compatibility experiment. Python standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
import build_profile as build


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    fd, name = tempfile.mkstemp(prefix='.mw4-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate(root):
    exe = root / 'sp26/sp26-cod.exe'
    if digest(exe.read_bytes()) != build.EXE_SHA256:
        raise RuntimeError('Unsupported executable: no changes made')
    rex = (root / 'sp26/rex_sp.dll').read_bytes()
    state = {build.REX_ORIGINAL_SHA256: 'unprepared', build.REX_PREPARED_SHA256: 'prepared'}.get(digest(rex))
    if state is None:
        raise RuntimeError('Unsupported rex_sp.dll: no changes made')
    return state


def require_game_closed():
    if platform.system() != 'Linux':
        return
    for proc in Path('/proc').iterdir():
        if proc.name.isdigit():
            try:
                running = (proc / 'comm').read_text().strip() == 'sp26-cod.exe'
            except (OSError, UnicodeError):
                continue
            if running:
                raise RuntimeError('Close MW4 before installing, restoring or launching a test')


def install(root, graphics):
    require_game_closed()
    state = root / '.mw4-linux'
    if state.exists():
        raise RuntimeError('Installation state exists. Use doctor or restore first.')
    validate(root)
    rex = bytearray((root / 'sp26/rex_sp.dll').read_bytes())
    rex[build.GATE_FILE_OFFSET:build.GATE_FILE_OFFSET + 5] = build.GATE_PREPARED
    desired = {'rex_sp.dll': bytes(rex)}
    for name, expected in build.GRAPHICS.items():
        data = (graphics / name).read_bytes()
        if digest(data) != expected:
            raise RuntimeError(f'Unverified graphics DLL: {name}')
        desired[name] = data
    # All inputs validated before creating state or changing game files.
    state.mkdir()
    receipt = {'schema': 1, 'status': 'prepared', 'files': {}}
    for name, data in desired.items():
        target = root / 'sp26' / name
        old = target.read_bytes() if target.exists() else None
        if old is not None:
            atomic(state / (name + '.backup'), old)
        receipt['files'][name] = {'before': digest(old) if old is not None else None, 'after': digest(data)}
    atomic(state / 'receipt.json', json.dumps(receipt, indent=2).encode())
    for name, data in desired.items():
        atomic(root / 'sp26' / name, data)
    receipt['status'] = 'installed'
    atomic(state / 'receipt.json', json.dumps(receipt, indent=2).encode())
    print('Installed build-pinned files; originals retained in .mw4-linux. Launch through this tool.')


def restore(root):
    require_game_closed()
    state = root / '.mw4-linux'
    receipt = json.loads((state / 'receipt.json').read_text())
    if receipt.get('schema') != 1 or set(receipt.get('files', {})) != {'rex_sp.dll', *build.GRAPHICS}:
        raise RuntimeError('Unrecognized restore receipt')
    # Validate every backup and destination before restoring any file.
    for name, item in receipt['files'].items():
        target = root / 'sp26' / name
        current = digest(target.read_bytes()) if target.exists() else None
        if current not in (item['before'], item['after']):
            raise RuntimeError(f'{name} changed since install; refusing to overwrite it')
        if item['before'] is not None and digest((state / (name + '.backup')).read_bytes()) != item['before']:
            raise RuntimeError(f'Backup checksum failed: {name}')
    for name, item in receipt['files'].items():
        target = root / 'sp26' / name
        if item['before'] is None:
            target.unlink(missing_ok=True)
        else:
            atomic(target, (state / (name + '.backup')).read_bytes())
    receipt['status'] = 'restored'
    atomic(state / 'receipt.json', json.dumps(receipt, indent=2).encode())
    print('Restored pre-install files. Audit receipt and backups retained.')


def launch(root, args):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('Launch requires Linux x86-64')
    if validate(root) != 'prepared':
        raise RuntimeError('Run install first')
    for name, expected in build.GRAPHICS.items():
        if digest((root / 'sp26' / name).read_bytes()) != expected:
            raise RuntimeError(f'Graphics DLL changed: {name}')
    scope = Path('/proc/sys/kernel/yama/ptrace_scope')
    if scope.exists() and int(scope.read_text()) > 1:
        raise RuntimeError('Host ptrace policy blocks this experiment; no policy changes made')
    for proc in Path('/proc').iterdir():
        if proc.name.isdigit():
            try:
                if (proc / 'comm').read_text().strip() == 'sp26-cod.exe':
                    raise RuntimeError('MW4 is already running; close it before an isolated launch')
            except (OSError, UnicodeError):
                pass
    from tracer import Tracer
    args.prefix.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, WINEPREFIX=str(args.prefix.resolve()), PROTONPATH=str(args.proton.resolve()),
               WINEDLLOVERRIDES='d3d12,d3d12core=n,b', UMU_RUNTIME_UPDATE='0', PROTON_ENABLE_WAYLAND='0')
    if args.home:
        env['HOME'] = str(args.home.resolve())
    logdir = root / '.mw4-linux' / ('run-' + time.strftime('%Y%m%dT%H%M%S'))
    logdir.mkdir(parents=True)
    pid = None
    with (logdir / 'umu.log').open('w') as output, (logdir / 'trace.jsonl').open('w') as events:
        child = subprocess.Popen([str(args.umu.resolve()), './sp26-cod.exe', args.game_argument],
                                 cwd=root / 'sp26', env=env, stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        def log(message, flush=True):
            print(message, flush=flush)
            print(message, file=events, flush=flush)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError(f'Launcher exited: see {logdir}/umu.log')
                for proc in Path('/proc').iterdir():
                    if not proc.name.isdigit():
                        continue
                    try:
                        maps = (proc / 'maps').read_text()
                        # Only the isolated executable we launched, never a basename-only match.
                        if str(root / 'sp26/sp26-cod.exe') in maps and str(root / 'sp26/rex_sp.dll') in maps:
                            pid = int(proc.name)
                            break
                    except (OSError, UnicodeError):
                        pass
                if pid is not None:
                    break
                time.sleep(.1)
            if pid is None:
                raise RuntimeError(f'Game mappings never appeared: see {logdir}/umu.log')
            (logdir / 'game.pid').write_text(str(pid))
            time.sleep(2)
            Tracer(pid, log=log).run()
            print(f'Helper detached. Game is running; logs: {logdir}', flush=True)
            return child.wait()
        except BaseException:
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['doctor', 'install', 'restore', 'launch'])
    parser.add_argument('--game', type=Path, required=True, help='Root containing sp26/')
    parser.add_argument('--graphics', type=Path, help='User-provided verified VKD3D DLL directory')
    parser.add_argument('--umu', type=Path)
    parser.add_argument('--proton', type=Path)
    parser.add_argument('--prefix', type=Path, help='Dedicated test prefix, never shared with another running game')
    parser.add_argument('--home', type=Path, help='Optional existing portable runtime HOME')
    parser.add_argument('--game-argument', help='Argument supplied by your existing offline campaign installation')
    args = parser.parse_args()
    root = args.game.resolve(strict=True)
    try:
        if args.command == 'doctor':
            print(json.dumps({'build': build.EXE_SHA256, 'rex_state': validate(root)}, indent=2))
        elif args.command == 'install':
            if args.graphics is None:
                parser.error('install requires --graphics')
            install(root, args.graphics)
        elif args.command == 'restore':
            restore(root)
        else:
            if not all((args.umu, args.proton, args.prefix, args.game_argument)):
                parser.error('launch requires --umu, --proton, --prefix and --game-argument')
            return launch(root, args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0
if __name__ == '__main__':
    sys.exit(main())
