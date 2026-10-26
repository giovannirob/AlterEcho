#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install_dir="$HOME/.local/bin"
assume_yes=0
no_path=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes) assume_yes=1 ;;
        --no-path) no_path=1 ;;
        --install-dir) shift; install_dir=${1:?Directory required} ;;
        *) echo "Invalid option: $1" >&2; exit 2 ;;
    esac
    shift
done
case "$install_dir" in /*) ;; *) echo 'The directory must be absolute.' >&2; exit 2 ;; esac
python_path="$project_root/.venv/bin/python"
[ -x "$python_path" ] || { echo 'First create .venv and install the project with pip install -e .' >&2; exit 1; }
echo "Launcher: $install_dir/alterecho"
if [ "$no_path" = 0 ]; then
    echo 'Adds the directory to user PATH in .profile and the shell file (Bash/Zsh). No sudo.'
fi
if [ "$assume_yes" = 0 ]; then
    printf 'Install? [y/N] '
    read -r answer
    case "$answer" in y|Y|yes|s|S|si|sì) ;; *) echo 'Installation cancelled.'; exit 0 ;; esac
fi
# Single-quote escaping keeps spaces, dollars and apostrophes literal in launchers/profiles.
quote_shell() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
mkdir -p "$install_dir"
{
    printf '#!/bin/sh\nexec '
    quote_shell "$python_path"
    printf ' -m alterecho "$@"\n'
} > "$install_dir/alterecho"
chmod +x "$install_dir/alterecho"
"$install_dir/alterecho" help >/dev/null
if [ "$no_path" = 0 ]; then
    profile_line="export PATH=$(quote_shell "$install_dir"):\"\$PATH\" # AlterEcho launcher"
    shell_profile="$HOME/.bashrc"
    case "${SHELL:-}" in */zsh) shell_profile="$HOME/.zshrc" ;; esac
    for profile in "$HOME/.profile" "$shell_profile"; do
        if ! grep -Fqx "$profile_line" "$profile" 2>/dev/null; then
            printf '\n%s\n' "$profile_line" >> "$profile"
        fi
    done
fi
echo 'Installation succeeded. Open a new terminal: alterecho. Help: alterecho help.'
echo 'After moving the project, recreate the virtualenv and reinstall.'
