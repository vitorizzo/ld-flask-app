document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.getElementById("homeTutorialDialog");
  const launcher = document.querySelector('[data-tutorial-context="home"]');
  const actionsRoot = document.querySelector("[data-home-tutorial-role]");
  if (!dialog || !launcher || !actionsRoot) return;

  const title = dialog.querySelector("[data-home-tutorial-step-title]");
  const description = dialog.querySelector("[data-home-tutorial-step-description]");
  const progress = dialog.querySelector("[data-home-tutorial-progress]");
  const icon = dialog.querySelector("[data-home-tutorial-icon]");
  const availability = dialog.querySelector("[data-home-tutorial-availability]");
  const dots = dialog.querySelector("[data-home-tutorial-dots]");
  const previous = dialog.querySelector("[data-home-tutorial-previous]");
  const next = dialog.querySelector("[data-home-tutorial-next]");
  const role = actionsRoot.dataset.homeTutorialRole || "visitatore";
  let steps = [];
  let currentStep = 0;

  const buildSteps = () => {
    const actions = [...actionsRoot.querySelectorAll(".quick-action[data-tutorial-description]")];
    const actionSteps = actions.map(action => ({
      title: action.querySelector("span")?.textContent.trim() || "Funzione",
      description: action.dataset.tutorialDescription,
      iconClass: action.querySelector("i")?.className || "fa-solid fa-circle-info",
      disabled: action.getAttribute("aria-disabled") === "true"
    }));

    return [
      {
        title: "Questa è la tua home",
        description: `Stai usando LDApp con il profilo ${role}. Per questo profilo sono mostrate ${actions.length} funzioni: vediamole insieme.`,
        iconClass: "fa-solid fa-house"
      },
      ...actionSteps,
      {
        title: "Ora sai da dove iniziare",
        description: "La home si adatta ai tuoi ruoli e permessi. Se questi cambiano, Lady App ti mostrerà automaticamente il tutorial aggiornato.",
        iconClass: "fa-solid fa-circle-check"
      }
    ];
  };

  const renderDots = () => {
    dots.replaceChildren();
    steps.forEach((_, index) => {
      const dot = document.createElement("span");
      dot.className = index === currentStep ? "is-active" : "";
      dots.appendChild(dot);
    });
  };

  const renderStep = () => {
    const step = steps[currentStep];
    title.textContent = step.title;
    description.textContent = step.description;
    progress.textContent = `Passaggio ${currentStep + 1} di ${steps.length}`;
    icon.replaceChildren();
    const iconElement = document.createElement("i");
    iconElement.className = step.iconClass;
    iconElement.setAttribute("aria-hidden", "true");
    icon.appendChild(iconElement);

    availability.hidden = !step.disabled;
    availability.textContent = step.disabled
      ? "Questa funzione è visibile, ma richiede un ruolo o un permesso aggiuntivo."
      : "";
    previous.disabled = currentStep === 0;
    next.innerHTML = currentStep === steps.length - 1
      ? 'Fine <i class="fa-solid fa-check" aria-hidden="true"></i>'
      : 'Avanti <i class="fa-solid fa-arrow-right" aria-hidden="true"></i>';
    renderDots();
  };

  launcher.addEventListener("click", () => {
    steps = buildSteps();
    currentStep = 0;
    renderStep();
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  });

  previous.addEventListener("click", () => {
    if (currentStep > 0) {
      currentStep -= 1;
      renderStep();
    }
  });

  next.addEventListener("click", () => {
    if (currentStep >= steps.length - 1) {
      dialog.close();
      return;
    }
    currentStep += 1;
    renderStep();
  });

  dialog.querySelector("[data-home-tutorial-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  });
});
