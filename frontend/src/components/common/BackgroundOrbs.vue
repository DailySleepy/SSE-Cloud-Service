<template>
  <div class="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
    <div class="bg-orb orb-1 top-[-100px] left-[-100px] w-[400px] h-[400px] bg-accent/20"></div>
    <div class="bg-orb orb-2 bottom-[-100px] right-[-100px] w-[300px] h-[300px] bg-blue-500/10 animate-delay-2000"></div>
  </div>
</template>

<style scoped>
.orb-1 {
  animation: pulse 8s infinite alternate;
}
.orb-2 {
  animation: pulse 8s infinite alternate-reverse;
}

@keyframes pulse {
  0% { transform: scale(1) translate(0, 0); }
  100% { transform: scale(1.1) translate(20px, 20px); }
}
</style>
