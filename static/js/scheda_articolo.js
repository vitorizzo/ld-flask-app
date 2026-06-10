document.addEventListener("DOMContentLoaded", function () {
    var modalElement = document.getElementById("fullscreen-carousel-modal");

    if (!modalElement) {
        return;
    }

    if (modalElement.parentElement !== document.body) {
        document.body.appendChild(modalElement);
    }

    modalElement.addEventListener("show.bs.modal", function () {
        document.body.classList.add("product-image-modal-open");
    });

    modalElement.addEventListener("hidden.bs.modal", function () {
        document.body.classList.remove("product-image-modal-open");
    });

    var fullscreenModal = bootstrap.Modal.getOrCreateInstance(modalElement);
    var fullscreenCarouselElement = document.getElementById("fullscreen-carousel");

    document.querySelectorAll(".product-img").forEach(function (image) {
        image.addEventListener("click", function () {
            var originalImages = Array.from(document.querySelectorAll("#productCarousel .carousel-item img"));
            var fullscreenImagesContainer = document.getElementById("fullscreen-carousel-images");
            var clickedIndex = Math.max(originalImages.indexOf(image), 0);

            if (!fullscreenImagesContainer || originalImages.length === 0) {
                return;
            }

            fullscreenImagesContainer.innerHTML = "";

            originalImages.forEach(function (sourceImage, index) {
                var carouselItem = document.createElement("div");
                carouselItem.classList.add("carousel-item");
                if (index === clickedIndex) {
                    carouselItem.classList.add("active");
                }

                var zoomedImage = document.createElement("img");
                zoomedImage.src = sourceImage.src;
                zoomedImage.alt = sourceImage.alt || "";
                zoomedImage.classList.add("d-block", "w-100");

                carouselItem.appendChild(zoomedImage);
                fullscreenImagesContainer.appendChild(carouselItem);
            });

            fullscreenModal.show();

            if (fullscreenCarouselElement) {
                bootstrap.Carousel.getOrCreateInstance(fullscreenCarouselElement).to(clickedIndex);
            }
        });
    });
});
