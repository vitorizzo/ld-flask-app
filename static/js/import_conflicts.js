console.log("Import Conflicts JS loaded");
let currentConflict = null;
const TYPE = "CODICE_RIASSEGNATO_O_DESC_DISCORDANTE";

function loadNext() {
    fetch(`/settings/next_conflict?type=${TYPE}`)
        .then(r => r.json())
        .then(data => {
            if (!data.ok || !data.conflict) {
                document.getElementById("out").textContent = "Nessun conflitto rimanente 🎉";
                document.getElementById("actions").classList.add("d-none");
                return;
            }

            currentConflict = data.conflict;
            document.getElementById("out").textContent =
                JSON.stringify(currentConflict, null, 2);

            document.getElementById("actions").classList.remove("d-none");
        })
        .catch(err => {
            document.getElementById("out").textContent = "Errore: " + err;
        });
}

document.addEventListener("click", e => {
    if (!e.target.dataset.action || !currentConflict) return;

    fetch("/settings/resolve_conflict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            id: currentConflict.id,
            action: e.target.dataset.action
        })
    })
    .then(r => r.json())
    .then(res => {
        document.getElementById("out").textContent =
            JSON.stringify(res, null, 2);
        loadNext();
    })
    .catch(err => alert(err));
});

document.addEventListener("DOMContentLoaded", loadNext);
