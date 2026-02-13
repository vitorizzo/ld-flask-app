const day = fetch("/cassa/api/day", { credentials: "same-origin" });
    if (!res.ok) throw new Error("get_menu_structure failed");
    return day.json();
console.log("giorno da backend")
console.log(day)