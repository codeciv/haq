#!/usr/bin/env python3
"""Layer-3 test that does not depend on any model: feed the checker real and invented legal references."""
from lawyer.checker import check

# (text, should_be_removed)
CASES = [
 ("File within 2 years under Section 69 of the Consumer Protection Act, 2019.", False),
 ("Rule 4(5) of the E-Commerce Rules says 48 hours.", False),
 ("Under Section 73 of the Indian Contract Act, 1872 you can claim compensation.", False),
 ("Section 11 of the Model Tenancy Act, 2021 caps the deposit, if your state adopted it.", False),
 ("You are a consumer under Section 2(7) of the Consumer Protection Act, 2019.", False),
 ("Free legal aid is available under Section 12 of the Legal Services Authorities Act, 1987.", False),
 ("No fee up to Rs 5 lakh under Rule 7 of the Consumer Protection (Consumer Disputes Redressal Commissions) Rules, 2020.", False),
 ("Unfair under Section 2(47) of the Consumer Protection Act, 2019. Under Rule 4(5) of the Consumer Protection (E-Commerce) Rules, 2020, they must reply.", False),
 ("Keep the invoice and act quickly. The Rules of your society don't matter here.", False),
 ("Under Section 420 of the IPC your landlord committed cheating.", True),
 ("Section 316 of the BNS covers criminal breach of trust.", True),
 ("As held in Ramesh Kumar v. State of Haryana, deposits must be returned.", True),
 ("See AIR 2019 SC 1234.", True),
 ("(2020) 5 SCC 123 says interest is payable.", True),
 ("The Supreme Court held that landlords must pay 18% interest.", True),
 ("The Delhi Rent Control Act, 1958 caps deposits.", True),
 ("Under Section 21A of the Tenant Deposit Protection Act, 2022 he must pay double.", True),
 ("Under Section 12 of the Consumer Protection Act you can claim triple damages.", True),
 ("Section 106 of the Transfer of Property Act needs 15 days notice.", True),
 ("Order XXXVII of the CPC allows a summary suit.", True),
 ("Section 138 of the NI Act applies to bounced cheques.", True),
 ("Under Rule 9 of the E-Commerce Rules refunds are due in 3 days.", True),
 ("Under Section 99 of the Consumer Protection Act, 2019 you get interest.", True),
]


# Known gap: a false legal CLAIM written without any section/Act/case looks like ordinary text.
KNOWN_GAPS = [
 "By law, landlords must pay 18% interest on late deposits.",
 "Courts always award double the deposit as a penalty.",
]


def main():
    tp = fp = tn = fn = 0
    for text, bad in CASES:
        r = check(text)
        cut = not r.ok
        tp += cut and bad; tn += (not cut) and (not bad); fp += cut and not bad; fn += (not cut) and bad
        flag = "ok " if cut == bad else "XX "
        print(f"{flag}{'REMOVED' if cut else 'kept   '} | {r.text}")
    print(f"\ninvented refs caught: {tp}/{tp+fn}   real refs wrongly removed: {fp}/{fp+tn}")
    print("\nKnown gap (no citation, so the checker cannot see it; handled only by the prompt + human review):")
    for t in KNOWN_GAPS:
        print("  ", "REMOVED" if not check(t).ok else "NOT CAUGHT", "|", t)


if __name__ == "__main__":
    main()
