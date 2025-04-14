function creaCaroselloImmagini(imgUrls) {
    const container = document.getElementById("contenitore-immagini-articolo");
    container.innerHTML = "";

    if (imgUrls.length === 0) return;

    const wrapper = document.createElement("div");
    wrapper.classList.add("carousel-wrapper");

    const track = document.createElement("div");
    track.classList.add("carousel-track");

    imgUrls.forEach((url, index) => {
        const img = document.createElement("img");
        img.src = url;
        img.alt = `Immagine ${index + 1}`;
        img.classList.add("carousel-image");
        img.addEventListener("click", () => apriImmagineFullScreen(imgUrls, index));
        track.appendChild(img);
    });

    wrapper.appendChild(track);
    container.appendChild(wrapper);
    aggiungiControlliCarosello(wrapper, track, imgUrls);
}

function aggiungiControlliCarosello(wrapper, track, imgUrls) {
    let currentSlide = 0;

    const btnPrev = document.createElement("button");
    btnPrev.textContent = "←";
    btnPrev.classList.add("carousel-btn", "prev");
    btnPrev.onclick = () => cambiaSlide(-1);

    const btnNext = document.createElement("button");
    btnNext.textContent = "→";
    btnNext.classList.add("carousel-btn", "next");
    btnNext.onclick = () => cambiaSlide(1);

    const dots = document.createElement("div");
    dots.classList.add("carousel-dots");

    imgUrls.forEach((_, i) => {
        const dot = document.createElement("span");
        dot.classList.add("dot");
        if (i === 0) dot.classList.add("active");
        dot.addEventListener("click", () => vaiASlide(i));
        dots.appendChild(dot);
    });

    wrapper.appendChild(btnPrev);
    wrapper.appendChild(btnNext);
    wrapper.appendChild(dots);

    let startX = 0;

    track.addEventListener("touchstart", e => startX = e.touches[0].clientX);
    track.addEventListener("touchend", e => {
        const endX = e.changedTouches[0].clientX;
        const diff = endX - startX;
        if (diff > 50) cambiaSlide(-1);
        if (diff < -50) cambiaSlide(1);
    });

    function cambiaSlide(dir) {
        currentSlide = (currentSlide + dir + imgUrls.length) % imgUrls.length;
        aggiornaSlide();
    }

    function vaiASlide(i) {
        currentSlide = i;
        aggiornaSlide();
    }

    function aggiornaSlide() {
        const offset = currentSlide * -100;
        track.style.transform = `translateX(${offset}%)`;
        dots.querySelectorAll(".dot").forEach(dot => dot.classList.remove("active"));
        dots.children[currentSlide].classList.add("active");
    }

    // ⌨️ Frecce tastiera
    document.addEventListener("keydown", e => {
        if (e.key === "ArrowLeft") cambiaSlide(-1);
        if (e.key === "ArrowRight") cambiaSlide(1);
    });
}

// 🔍 Modal full screen
function apriImmagineFullScreen(imgUrls, startIndex = 0) {
    const modal = document.createElement("div");
    modal.classList.add("fullscreen-modal");

    const track = document.createElement("div");
    track.classList.add("fullscreen-track");

    imgUrls.forEach((url, index) => {
        const img = document.createElement("img");
        img.src = url;
        img.alt = `Immagine ${index + 1}`;
        img.classList.add("fullscreen-image");
        track.appendChild(img);
    });

    const btnClose = document.createElement("button");
    btnClose.textContent = "✖";
    btnClose.classList.add("btn-close-fullscreen");
    btnClose.addEventListener("click", () => modal.remove());

    modal.appendChild(track);
    modal.appendChild(btnClose);
    document.body.appendChild(modal);

    let current = startIndex;
    track.style.transform = `translateX(${-100 * current}%)`;

    modal.addEventListener("click", e => {
        if (e.target === modal) modal.remove();
    });

    document.addEventListener("keydown", function handler(e) {
        if (!document.body.contains(modal)) return document.removeEventListener("keydown", handler);
        if (e.key === "Escape") modal.remove();
        if (e.key === "ArrowRight") nav(1);
        if (e.key === "ArrowLeft") nav(-1);
    });

    function nav(dir) {
        current = (current + dir + imgUrls.length) % imgUrls.length;
        track.style.transform = `translateX(${-100 * current}%)`;
    }

    // Swipe mobile
    let startX = 0;
    track.addEventListener("touchstart", e => startX = e.touches[0].clientX);
    track.addEventListener("touchend", e => {
        const diff = e.changedTouches[0].clientX - startX;
        if (diff > 50) nav(-1);
        if (diff < -50) nav(1);
    });
}
