const day = await fetch("/cassa/api/day", { credentials: "same-origin" });
    if (!res.ok) throw new Error("get_menu_structure failed");
    return await day.json();
console.log("giorno da backend")
console.log(day)