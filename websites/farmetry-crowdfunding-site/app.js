// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Animate progress bar on load
window.addEventListener('load', () => {
    const progressFill = document.querySelector('.progress-fill');
    if (progressFill) {
        progressFill.style.width = '0%';
        setTimeout(() => {
            progressFill.style.width = '28%';
        }, 500);
    }
});

// Back This Project button handler
const backButtons = document.querySelectorAll('.btn-primary');
backButtons.forEach(button => {
    button.addEventListener('click', () => {
        // In a real implementation, this would open a payment modal
        alert('Thank you for your interest! Payment integration coming soon.\n\nFor now, this is a demo crowdfunding page.');
    });
});

// Animate stats on scroll
const observerOptions = {
    threshold: 0.5,
    rootMargin: '0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '0';
            entry.target.style.transform = 'translateY(20px)';
            setTimeout(() => {
                entry.target.style.transition = 'all 0.6s ease';
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }, 100);
        }
    });
}, observerOptions);

document.querySelectorAll('.stat-card, .reward-card').forEach(card => {
    observer.observe(card);
});

// Add parallax effect to grid pattern
window.addEventListener('scroll', () => {
    const scrolled = window.pageYOffset;
    const gridPattern = document.querySelector('.grid-pattern');
    if (gridPattern) {
        gridPattern.style.transform = `translateY(${scrolled * 0.3}px)`;
    }
});

// Email capture functionality (for newsletter/updates)
function captureEmail(email) {
    const websiteId = 'ace2ab62-e2dd-4b7f-8fdb-923a1587db25';
    
    return fetch(`https://aicofounder.com/api/website/${websiteId}/capture-email`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Thanks for subscribing! We\'ll keep you updated.');
        }
        return data;
    })
    .catch(error => {
        console.error('Email capture failed:', error);
        alert('Something went wrong. Please try again.');
    });
}

// Add dynamic counter animation
function animateValue(element, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const value = Math.floor(progress * (end - start) + start);
        element.textContent = '$' + value.toLocaleString();
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

// Animate funding amount on load
window.addEventListener('load', () => {
    const fundedElement = document.querySelector('.glow-box .glow-text');
    if (fundedElement) {
        animateValue(fundedElement, 0, 2847, 2000);
    }
});
