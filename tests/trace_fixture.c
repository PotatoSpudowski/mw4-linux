#include <stdio.h>
#include <unistd.h>
volatile int gate = 1;
__attribute__((naked,noinline)) void checkpoint(void) { __asm__("nop; ret"); }
int main(void) {
    printf("%p %p\n", (void *)&gate, (void *)&checkpoint); fflush(stdout);
    while (gate) usleep(1000);
    checkpoint();
    puts("completed");
    return 0;
}
