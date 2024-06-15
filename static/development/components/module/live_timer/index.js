const allTimers = document.querySelectorAll(".live-timer");

allTimers.forEach((timerElement) => {
  const endTime = new Date(timerElement.dataset.endTime);

  const updateTimer = () => {
    const now = new Date();
    const timeRemaining = endTime - now;

    if (timeRemaining <= 0) {
      timerElement.textContent = "00:00:00";
      clearInterval(intervalId);
      return;
    }

    const days = String(
      Math.floor(timeRemaining / (1000 * 60 * 60 * 24))
    ).padStart(2, "0");
    const hours = String(
      Math.floor((timeRemaining / (1000 * 60 * 60)) % 24)
    ).padStart(2, "0");
    const minutes = String(
      Math.floor((timeRemaining / (1000 * 60)) % 60)
    ).padStart(2, "0");
    const seconds = String(Math.floor((timeRemaining / 1000) % 60)).padStart(
      2,
      "0"
    );

    timerElement.textContent = `${
      Number(days) ? `${days} днів та` : ""
    }  ${hours}:${minutes}:${seconds}`;
  };

  updateTimer(); // Initial call to show the timer immediately
  const intervalId = setInterval(updateTimer, 1000);
});
