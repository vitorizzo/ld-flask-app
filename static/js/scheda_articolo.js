document.addEventListener("DOMContentLoaded", function () {
    var productCarousel = document.getElementById("productCarousel");
    var modalElement = document.getElementById("fullscreen-carousel-modal");

    if (!modalElement) {
        console.warn("⚠️ Modale 'fullscreen-carousel-modal' non trovata.");
        return;
    }

    var fullscreenModal = new bootstrap.Modal(modalElement);

    document.querySelectorAll(".product-img").forEach(img => {
        img.addEventListener("click", function () {
            var originalImages = document.querySelectorAll("#productCarousel .carousel-item img");
            var fullscreenImagesContainer = document.getElementById("fullscreen-carousel-images");

            fullscreenImagesContainer.innerHTML = "";

            originalImages.forEach((img, index) => {
                var newCarouselItem = document.createElement("div");
                newCarouselItem.classList.add("carousel-item");
                if (index === 0) newCarouselItem.classList.add("active");

                var newImg = document.createElement("img");
                newImg.src = img.src;
                newImg.classList.add("d-block", "w-100");

                newCarouselItem.appendChild(newImg);
                fullscreenImagesContainer.appendChild(newCarouselItem);
            });

            fullscreenModal.show();
        });
    });
});
