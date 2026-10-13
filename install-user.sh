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
        --install-dir) shift; install_dir=${1:?Manca la cartella} ;;
        *) echo "Opzione non valida: $1" >&2; exit 2 ;;
    esac
    shift
done
case "$install_dir" in /*) ;; *) echo 'La cartella deve essere assoluta.' >&2; exit 2 ;; esac
python_path="$project_root/.venv/bin/python"
[ -x "$python_path" ] || { echo 'Prima crea .venv e installa il progetto con pip install -e .' >&2; exit 1; }
echo "Launcher: $install_dir/alterecho"
if [ "$no_path" = 0 ]; then
    echo 'Aggiunge la cartella al PATH utente in .profile e nel file della shell (Bash/Zsh). Nessun sudo.'
fi
if [ "$assume_yes" = 0 ]; then
    printf 'Installare? [s/N] '
    read -r answer
    case "$answer" in s|S|si|sì) ;; *) echo 'Installazione annullata.'; exit 0 ;; esac
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
echo 'Installazione riuscita. Apri un nuovo terminale: alterecho. Guida: alterecho help.'
echo 'Se sposti il progetto, ricrea il virtualenv e ripeti questa installazione.'
